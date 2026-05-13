from __future__ import annotations

import time

from backend.app.agent.extractor import SlotExtractor, build_follow_up_questions
from backend.app.agent.state import MultiAgentState
from backend.app.rules.disease_risk import DiseaseRiskEvaluator


class DiseaseAgent:
    def __init__(
        self,
        *,
        slot_extractor: SlotExtractor | None = None,
        risk_evaluator: DiseaseRiskEvaluator | None = None,
    ) -> None:
        self.slot_extractor = slot_extractor or SlotExtractor()
        self.risk_evaluator = risk_evaluator or DiseaseRiskEvaluator()

    def run(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "disease_agent"

        slots = self.slot_extractor.extract(state.normalized_query or state.user_query)
        state.extracted_slots = slots.model_dump()
        state.tool_results["slot_extractor"] = state.extracted_slots

        questions = build_follow_up_questions(slots)
        if questions:
            state.disease_assessment = {
                "status": "follow_up",
                "follow_up_questions": questions,
                "missing_info": self._missing_info_from_questions(questions),
            }
            state.draft_answer = "请先补充以下信息：\n" + "\n".join(f"- {item}" for item in questions)
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
            state.draft_answer = "请先补充以下信息：\n" + "\n".join(f"- {item}" for item in questions)
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
