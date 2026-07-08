from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import uuid4

from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.disease_evidence_gate import DiseaseEvidenceGate
from backend.app.agent.disease_reasoning import DiseaseReasoningAgent
from backend.app.agent.measurement_agent import MeasurementAgent
from backend.app.agent.rag_agent import RagAgent
from backend.app.agent.rag_answer_policy import (
    NO_ANSWER_TEXT,
    SAFETY_REFUSAL_TEXT,
    RagAnswerPolicyDecision,
    classify_rag_answer_policy,
)
from backend.app.agent.response_agent import ResponseAgent
from backend.app.agent.safety_agent import SafetyAgent
from backend.app.agent.safety_precheck import SafetyPrecheck
from backend.app.agent.state import MultiAgentState
from backend.app.agent.supervisor import SupervisorAgent
from backend.app.agent.verifier_agent import VerifierAgent
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.model.answer_generator import AnswerGenerator
from backend.app.model.base import BaseModelClient
from backend.app.model.query_normalizer import normalize_query_with_router
from backend.app.model.router import ModelRouteRequest, ModelRouter, ModelTaskType
from backend.app.schemas.measurement import MeasurementInput
from backend.app.schemas.rag_server import RagSearchResult
from backend.app.services.feature_flag_service import FeatureFlagService
from backend.app.services.memory_service import MemoryEvent, MemoryFact, MemoryService, build_measurement_memory_fact
from backend.app.services.session_context_service import SessionContextData, SessionContextService


async def run_general_qa_graph(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    settings: Settings | None = None,
    query_normalizer_client: BaseModelClient | None = None,
) -> MultiAgentState:
    state = MultiAgentState(session_id=session_id or _new_session_id(), request_id=request_id, user_query=query)
    await _maybe_normalize_query(state, settings=settings, client=query_normalizer_client)
    SupervisorAgent().route(state)
    record_shadow_route(state, settings=settings)
    await RagAgent(rag_client or FakeRagServerClient()).run(state)
    policy = _apply_rag_answer_policy(state)
    if policy.should_use_retrieved_contexts:
        _compose_rag_draft(state)
    VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


async def run_disease_graph(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_context_service: SessionContextService | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    animal_id: str | None = None,
    memory_service: MemoryService | None = None,
    unsafe_draft_for_test: str | None = None,
    settings: Settings | None = None,
    query_normalizer_client: BaseModelClient | None = None,
    primary_llm_client: Any | None = None,
) -> MultiAgentState:
    resolved_session_id = session_id or _new_session_id()
    state = MultiAgentState(session_id=resolved_session_id, request_id=request_id, user_query=query)
    await _maybe_normalize_query(state, settings=settings, client=query_normalizer_client)
    SupervisorAgent().route(state)
    record_shadow_route(state, settings=settings)
    if session_context_service is not None:
        previous_context = None
        if not session_context_service.clear_conflicted_context(resolved_session_id, query):
            previous_context = session_context_service.get_context(resolved_session_id)
        if previous_context is not None:
            state.session_context = previous_context.model_dump(mode="json")
            state.normalized_query = merge_session_slots(query, previous_context)
    DiseaseAgent(settings=settings, primary_llm_client=primary_llm_client).run(state)
    if session_context_service is not None:
        _save_disease_context(session_context_service, state)
    _maybe_write_user_confirmed_facts(
        state,
        animal_id=animal_id,
        memory_service=memory_service,
        settings=settings,
    )
    if state.rag_query:
        disease_draft = state.draft_answer or ""
        await RagAgent(rag_client or FakeRagServerClient()).run(state)
        gate_result = DiseaseEvidenceGate().evaluate(state)
        state.tool_results["disease_evidence_gate"] = asdict(gate_result)
        state.agent_trace.append(
            {
                "node": "disease_evidence_gate",
                "status": "passed" if gate_result.allowed else "blocked",
                "allowed": gate_result.allowed,
                "error_code": gate_result.error_code,
                "evidence_ref_count": len(gate_result.evidence_refs),
                "latency_ms": 0,
            }
        )
        DiseaseReasoningAgent(settings=settings, primary_llm_client=primary_llm_client).run(state)
        if _disease_reasoning_takeover_enabled(settings) and _compose_disease_reasoning_draft(state):
            pass
        elif gate_result.allowed:
            _compose_rag_draft(state, prefix=disease_draft)
        else:
            state.draft_answer = (
                f"{disease_draft}\n\n"
                "当前检索结果缺少可追溯来源，不能基于证据展开疾病分析。"
                "请补充更多现场信息，或联系兽医进行判断。"
            )
        if unsafe_draft_for_test is not None:
            state.draft_answer = unsafe_draft_for_test
        VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


def merge_session_slots(query: str, context: SessionContextData) -> str:
    parts = [query]
    fields = context.confirmed_case_fields or {}
    species = fields.get("species") or context.last_species
    if species:
        parts.append(_species_label(str(species)))
        parts.append(f"[species={species}]")
    raw_symptoms = fields.get("symptoms") or context.last_symptoms
    symptoms = raw_symptoms if isinstance(raw_symptoms, list) else [raw_symptoms]
    for symptom in symptoms:
        if not symptom:
            continue
        parts.append(_symptom_label(str(symptom)))
        parts.append(f"[symptom={symptom}]")
    for field in ("duration_days", "temperature_c", "group_outbreak"):
        if field in fields and fields[field] is not None:
            parts.append(f"[{field}={_context_tag_value(fields[field])}]")
    return " ".join(part for part in parts if part)


async def run_measurement_graph(
    measurement: MeasurementInput,
    *,
    session_id: str | None = None,
    memory_service: MemoryService | None = None,
    settings: Settings | None = None,
) -> MultiAgentState:
    state = MultiAgentState(
        session_id=session_id or _new_session_id(),
        user_query=f"body measurement analysis for {measurement.animal_id}",
    )
    SupervisorAgent().route(state)
    record_shadow_route(state, settings=settings)
    MeasurementAgent(settings=settings).run(state, measurement)
    _maybe_write_measurement_memory(
        state,
        measurement,
        memory_service=memory_service,
        settings=settings,
    )
    VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


def _compose_rag_draft(state: MultiAgentState, *, prefix: str | None = None) -> None:
    rag_result = state.tool_results.get("livestock_rag_search")
    if isinstance(rag_result, dict):
        evidence_answer = AnswerGenerator().compose_with_citations(RagSearchResult.model_validate(rag_result))
        state.draft_answer = f"{prefix}\n\n{evidence_answer}" if prefix else evidence_answer


def _apply_rag_answer_policy(state: MultiAgentState) -> RagAnswerPolicyDecision:
    policy = classify_rag_answer_policy(state.normalized_query or state.user_query)
    if policy.warning:
        state.tool_results["rag_answer_policy"] = policy.model_dump()
    if policy.force_no_answer:
        state.retrieved_contexts.clear()
        state.draft_answer = NO_ANSWER_TEXT
    elif policy.force_safety_refusal:
        state.retrieved_contexts.clear()
        state.draft_answer = SAFETY_REFUSAL_TEXT
    return policy


def _disease_reasoning_takeover_enabled(settings: Settings | None) -> bool:
    return bool(settings and settings.disease_llm.enabled and not settings.disease_llm.shadow_mode)


def _compose_disease_reasoning_draft(state: MultiAgentState) -> bool:
    record = state.tool_results.get("disease_reasoning")
    if not isinstance(record, dict) or record.get("status") != "success" or not isinstance(record.get("reasoning"), dict):
        return False
    reasoning = record["reasoning"]
    lines = ["以下内容基于已检索到的资料整理，不能替代兽医现场判断。"]
    _append_reasoning_section(lines, "可能相关因素", reasoning.get("contributing_factors") or [])
    if reasoning.get("uncertainties"):
        lines.append("仍需确认：")
        lines.extend(f"- {item}" for item in reasoning["uncertainties"])
    _append_reasoning_section(lines, "可先做的安全处理", reasoning.get("safe_actions") or [])
    _append_reasoning_section(lines, "需要联系兽医的情况", reasoning.get("vet_triggers") or [])
    state.draft_answer = "\n".join(lines)
    state.tool_results["disease_reasoning_takeover"] = {"applied": True}
    return True


def _append_reasoning_section(lines: list[str], title: str, items: list[dict]) -> None:
    if not items:
        return
    lines.append(f"{title}：")
    for item in items:
        text = str(item.get("text") or "").strip()
        refs = _format_reasoning_refs(item.get("evidence_refs") or [])
        lines.append(f"- {text}{refs}")


def _format_reasoning_refs(refs: list[dict]) -> str:
    formatted = []
    for ref in refs:
        if isinstance(ref, dict) and ref.get("source_uri") and ref.get("chunk_id"):
            formatted.append(f"{ref['source_uri']}#{ref['chunk_id']}")
    return f"（依据：{'; '.join(formatted)}）" if formatted else ""


def record_shadow_route(state: MultiAgentState, *, settings: Settings | None = None) -> None:
    app_settings = settings or Settings()
    if not FeatureFlagService(app_settings).model_router_enabled:
        return

    safety = SafetyPrecheck().classify(state.normalized_query or state.user_query)
    request = ModelRouteRequest(
        task_type=_model_task_type(state),
        safety_level=safety.level,
        requires_final_answer=_requires_final_answer(state),
        user_query=state.normalized_query or state.user_query,
        metadata={"intent": state.intent or "unknown"},
    )
    decision = ModelRouter(app_settings).route(request)
    payload = {
        "safety_precheck": safety.model_dump(),
        "route_request": request.model_dump(),
        "route_decision": decision.model_dump(),
    }
    state.tool_results["model_router_shadow"] = payload
    state.agent_trace.append(
        {
            "node": "model_router_shadow",
            "status": "success",
            "route_mode": decision.route_mode,
            "selected_model": decision.selected_model,
            "shadow_model": decision.shadow_model,
            "safety_level": safety.level,
            "local_candidate_allowed": decision.local_candidate_allowed,
        }
    )


async def _maybe_normalize_query(
    state: MultiAgentState,
    *,
    settings: Settings | None = None,
    client: BaseModelClient | None = None,
) -> None:
    app_settings = settings or Settings()
    if not FeatureFlagService(app_settings).model_router_enabled:
        return

    result = await normalize_query_with_router(state.user_query, settings=app_settings, client=client)
    state.normalized_query = result.normalized_query
    if result.route_mode == "disabled":
        return

    state.tool_results["query_normalizer_router"] = {
        "route_request": result.route_request,
        "route_decision": result.route_decision,
        "fallback_used": result.fallback_used,
        "fallback_reason": result.fallback_reason,
        "warnings": result.warnings,
    }
    if result.fallback_used:
        record_model_fallback(
            state,
            component="query_normalizer",
            selected_model=result.selected_model,
            fallback_reason=result.fallback_reason,
            route_mode=result.route_mode,
        )
    state.agent_trace.append(
        {
            "node": "query_normalizer",
            "status": "success",
            "route_mode": result.route_mode,
            "selected_model": result.selected_model,
            "fallback_used": result.fallback_used,
            "fallback_reason": result.fallback_reason,
        }
    )


def record_model_fallback(
    state: MultiAgentState,
    *,
    component: str,
    selected_model: str | None,
    fallback_reason: str | None,
    route_mode: str | None,
) -> None:
    state.tool_results.setdefault("model_fallbacks", []).append(
        {
            "component": component,
            "selected_model": selected_model,
            "fallback_reason": fallback_reason,
            "route_mode": route_mode,
        }
    )


def _model_task_type(state: MultiAgentState) -> ModelTaskType:
    if state.intent == "measurement_analysis":
        return "measurement_analysis"
    return "final_answer"


def _requires_final_answer(state: MultiAgentState) -> bool:
    return state.intent in {"general_qa", "disease_consultation", "out_of_scope"}


def _maybe_write_measurement_memory(
    state: MultiAgentState,
    measurement: MeasurementInput,
    *,
    memory_service: MemoryService | None,
    settings: Settings | None,
) -> None:
    if not _memory_write_enabled(settings) or memory_service is None:
        return
    fact = build_measurement_memory_fact(
        measurement,
        source="user_confirmed",
        metadata={"session_id": state.session_id, "agent": "measurement_agent"},
    )
    event = memory_service.maybe_write_memory(fact)
    _record_memory_write(state, event)


def _maybe_write_user_confirmed_facts(
    state: MultiAgentState,
    *,
    animal_id: str | None,
    memory_service: MemoryService | None,
    settings: Settings | None,
) -> None:
    if not animal_id or not _memory_write_enabled(settings) or memory_service is None:
        return
    fact = _build_user_confirmed_observation_fact(state, animal_id)
    if fact is None:
        return
    event = memory_service.maybe_write_memory(fact)
    _record_memory_write(state, event)


def _build_user_confirmed_observation_fact(state: MultiAgentState, animal_id: str) -> MemoryFact | None:
    slots = state.extracted_slots or {}
    value: dict[str, object] = {}
    for field in ("species", "age_stage", "duration_days", "temperature_c", "group_outbreak"):
        slot_value = slots.get(field)
        if slot_value is not None:
            value[field] = slot_value
    symptoms = list(slots.get("symptoms") or [])
    if symptoms:
        value["symptoms"] = symptoms
    if not value:
        return None
    return MemoryFact(
        subject_type="animal",
        subject_id=animal_id,
        fact_type="user_confirmed_observation",
        value=value,
        source="user_confirmed",
        metadata={"session_id": state.session_id, "agent": "disease_agent"},
    )


def _memory_write_enabled(settings: Settings | None) -> bool:
    if settings is None:
        return False
    return FeatureFlagService(settings).memory_write_enabled


def _record_memory_write(state: MultiAgentState, event: MemoryEvent | None) -> None:
    if event is None:
        return
    state.tool_results.setdefault("long_term_memory", []).append(
        {
            "event_id": event.event_id,
            "subject_type": event.subject_type,
            "subject_id": event.subject_id,
            "fact_type": event.payload.get("fact_type"),
            "source": event.source,
        }
    )


def _new_session_id() -> str:
    return f"s_{uuid4().hex}"


def _save_disease_context(session_context_service: SessionContextService, state: MultiAgentState) -> None:
    slots = state.extracted_slots
    disease_assessment = state.disease_assessment or {}
    pending_slots = list(disease_assessment.get("missing_info") or [])
    confirmed_case_fields = _confirmed_case_fields(slots)
    slot_sources = {
        "species": "user_confirmed" if slots.get("species") else "missing",
        "symptoms": "user_confirmed" if slots.get("symptoms") else "missing",
        "duration_days": "user_confirmed" if slots.get("duration_days") is not None else "missing",
        "temperature_c": "user_confirmed" if slots.get("temperature_c") is not None else "missing",
        "group_outbreak": "user_confirmed" if slots.get("group_outbreak") is not None else "missing",
    }
    if disease_assessment.get("risk_level"):
        slot_sources["risk_level"] = "tool_result"

    session_context_service.save_context(
        SessionContextData(
            session_id=state.session_id,
            last_intent="disease_consultation",
            last_species=slots.get("species"),
            last_symptoms=list(slots.get("symptoms") or []),
            pending_slots=pending_slots,
            confirmed_case_fields=confirmed_case_fields,
            pending_questions=pending_slots,
            answered_questions=list(confirmed_case_fields.keys()),
            last_understanding=_last_disease_understanding(state),
            evidence_refs=_rag_evidence_refs(state),
            slot_sources=slot_sources,
            risk_context_status="incomplete" if pending_slots else str(disease_assessment.get("risk_level") or "complete"),
        )
    )


def _confirmed_case_fields(slots: dict) -> dict[str, object]:
    confirmed: dict[str, object] = {}
    for field in ("species", "age_stage", "duration_days", "temperature_c", "group_outbreak"):
        value = slots.get(field)
        if value is not None:
            confirmed[field] = value
    symptoms = list(slots.get("symptoms") or [])
    if symptoms:
        confirmed["symptoms"] = symptoms
    return confirmed


def _last_disease_understanding(state: MultiAgentState) -> dict[str, object] | None:
    for key in ("disease_understanding", "disease_understanding_shadow"):
        result = state.tool_results.get(key)
        if isinstance(result, dict) and isinstance(result.get("understanding"), dict):
            return dict(result["understanding"])
    return None


def _rag_evidence_refs(state: MultiAgentState) -> list[dict[str, object]]:
    rag_result = state.tool_results.get("livestock_rag_search")
    if not isinstance(rag_result, dict):
        return []
    refs: list[dict[str, object]] = []
    for hit in rag_result.get("hits") or []:
        if isinstance(hit, dict) and (hit.get("source_uri") or hit.get("chunk_id")):
            refs.append({"source_uri": hit.get("source_uri"), "chunk_id": hit.get("chunk_id")})
    return refs


def _context_tag_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _species_label(species: str) -> str:
    return {"cattle": "牛", "sheep": "羊", "pig": "猪"}.get(species, species)


def _symptom_label(symptom: str) -> str:
    return {
        "diarrhea": "腹泻",
        "depression": "精神差",
        "low_appetite": "不吃草",
        "cough": "咳嗽",
        "breathing_difficulty": "呼吸困难",
    }.get(symptom, symptom)
