from __future__ import annotations

import time
from typing import Any

from backend.app.agent.extractor import DiseaseSlots, SlotExtractor, build_follow_up_questions
from backend.app.agent.safety_precheck import SafetyPrecheck
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.router import ModelRouteRequest, ModelRouter
from backend.app.rules.disease_risk import DiseaseRiskEvaluator


FOLLOW_UP_INTRO = "我先按疾病问诊处理。采食或精神异常可能和发热、消化问题、饲料变化、寄生虫或应激有关；为了判断风险，请先补充以下信息："


class DiseaseAgent:
    def __init__(
        self,
        *,
        slot_extractor: SlotExtractor | None = None,
        risk_evaluator: DiseaseRiskEvaluator | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.slot_extractor = slot_extractor or SlotExtractor()
        self.risk_evaluator = risk_evaluator or DiseaseRiskEvaluator()
        self.settings = settings or Settings()

    def run(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "disease_agent"

        slots = self.extract_slots_with_router(state.normalized_query or state.user_query, state=state)
        state.extracted_slots = slots.model_dump()
        state.tool_results["slot_extractor"] = state.extracted_slots

        questions = build_follow_up_questions(slots)
        if questions:
            state.disease_assessment = {
                "status": "follow_up",
                "follow_up_questions": questions,
                "missing_info": self._missing_info_from_questions(questions),
            }
            state.draft_answer = FOLLOW_UP_INTRO + "\n" + "\n".join(f"- {item}" for item in questions)
            self._append_trace(
                state,
                status="follow_up",
                latency_ms=self._latency_ms(started_at),
                missing_info=state.disease_assessment["missing_info"],
            )
            return state

        risk_result = self.risk_evaluator.evaluate(**state.extracted_slots)
        state.tool_results["disease_risk_evaluator"] = risk_result.model_dump()
        if risk_result.status == "missing_info":
            questions = self._questions_from_missing_info(risk_result.missing_info)
            state.disease_assessment = {
                **risk_result.model_dump(),
                "status": "follow_up",
                "follow_up_questions": questions,
            }
            state.draft_answer = FOLLOW_UP_INTRO + "\n" + "\n".join(f"- {item}" for item in questions)
            self._append_trace(
                state,
                status="follow_up",
                latency_ms=self._latency_ms(started_at),
                risk_level=risk_result.risk_level,
                missing_info=risk_result.missing_info,
            )
            return state

        state.disease_assessment = risk_result.model_dump()
        state.risk_level = risk_result.risk_level
        state.rag_query = f"{state.user_query} 风险等级 {risk_result.risk_level} 处理原则"
        state.draft_answer = self._build_consultation_draft(risk_result.model_dump())
        self._append_trace(
            state,
            status=risk_result.status,
            latency_ms=self._latency_ms(started_at),
            risk_level=risk_result.risk_level,
            missing_info=risk_result.missing_info,
        )
        return state

    def extract_slots_with_router(self, query: str, *, state: MultiAgentState | None = None) -> DiseaseSlots:
        rule_slots = self.slot_extractor.extract(query)
        safety = SafetyPrecheck().classify(query)
        route_request = ModelRouteRequest(
            task_type="structured_extraction",
            safety_level=safety.level,
            requires_final_answer=False,
            user_query=query,
            metadata={"component": "disease_slot_extraction"},
        )
        decision = ModelRouter(self.settings).route(route_request)
        if decision.selected_model != "local_small":
            self._record_slot_router(
                state,
                route_request=route_request.model_dump(),
                route_decision=decision.model_dump(),
                fallback_used=True,
                fallback_reason=decision.blocked_reason or "local_takeover_not_selected",
            )
            return rule_slots

        try:
            local_slots = DiseaseSlots.model_validate(self.render_local_slots(query))
        except ValueError:
            self._record_slot_router(
                state,
                route_request=route_request.model_dump(),
                route_decision=decision.model_dump(),
                fallback_used=True,
                fallback_reason="local_slot_schema_invalid",
            )
            return rule_slots
        except Exception as exc:
            self._record_slot_router(
                state,
                route_request=route_request.model_dump(),
                route_decision=decision.model_dump(),
                fallback_used=True,
                fallback_reason=f"local_slot_error:{exc.__class__.__name__}",
            )
            return rule_slots

        self._record_slot_router(
            state,
            route_request=route_request.model_dump(),
            route_decision=decision.model_dump(),
            fallback_used=False,
            fallback_reason=None,
        )
        return local_slots

    def render_local_slots(self, query: str) -> dict[str, Any]:
        return self.slot_extractor.extract(query).model_dump()

    def _record_slot_router(
        self,
        state: MultiAgentState | None,
        *,
        route_request: dict[str, Any],
        route_decision: dict[str, Any],
        fallback_used: bool,
        fallback_reason: str | None,
    ) -> None:
        if state is None or route_decision["route_mode"] == "disabled":
            return
        state.tool_results["disease_slot_router"] = {
            "route_request": route_request,
            "route_decision": route_decision,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
        }

    def _build_consultation_draft(self, risk_result: dict) -> str:
        need_vet = "是" if risk_result["need_vet"] else "视情况"
        need_isolation = "是" if risk_result["need_isolation"] else "否"
        return (
            f"初步风险等级：{risk_result['risk_level']}。\n"
            f"{risk_result['reason']}\n"
            f"是否建议联系兽医：{need_vet}。\n"
            f"是否建议隔离观察：{need_isolation}。"
        )

    def _missing_info_from_questions(self, questions: list[str]) -> list[str]:
        fields: list[str] = []
        for question in questions:
            if "持续" in question:
                fields.append("duration_days")
            elif "体温" in question:
                fields.append("temperature_c")
            elif "群体" in question:
                fields.append("group_outbreak")
            elif "症状" in question:
                fields.append("symptoms")
        return fields

    def _questions_from_missing_info(self, missing_info: list[str]) -> list[str]:
        question_by_field = {
            "species": "请补充动物种类，例如牛、羊或猪？",
            "duration_days": "症状已经持续多久了？",
            "temperature_c": "目前体温是多少？",
            "group_outbreak": "是否有群体发病或多头同时出现类似症状？",
            "symptoms": "主要症状有哪些，例如腹泻、咳嗽、精神差或采食下降？",
        }
        return [question_by_field[field] for field in missing_info if field in question_by_field][:3]

    def _append_trace(
        self,
        state: MultiAgentState,
        *,
        status: str,
        latency_ms: int,
        risk_level: str | None = None,
        missing_info: list[str] | None = None,
    ) -> None:
        state.agent_trace.append(
            {
                "node": "disease_agent",
                "status": status,
                "risk_level": risk_level,
                "missing_info": missing_info or [],
                "latency_ms": latency_ms,
            }
        )

    def _latency_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))
