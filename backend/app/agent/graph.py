from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.app.agent.direct_answer_agent import DirectAnswerAgent, fallback_direct_answer
from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.grounded_answer_agent import GroundedAnswerAgent
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
from backend.app.model.base import BaseModelClient
from backend.app.model.intent_router import IntentRoutingResult, route_intent_with_model
from backend.app.model.query_normalizer import normalize_query_with_router
from backend.app.model.router import ModelRouteRequest, ModelRouter, ModelTaskType
from backend.app.schemas.measurement import MeasurementInput
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
    primary_llm_client: Any | None = None,
) -> MultiAgentState:
    state = MultiAgentState(session_id=session_id or _new_session_id(), request_id=request_id, user_query=query)
    await _maybe_normalize_query(state, settings=settings, client=query_normalizer_client)
    route_override = await _maybe_route_intent_with_model(state, settings=settings)
    SupervisorAgent().route(state, route_override=route_override)
    if route_override is None:
        record_shadow_route(state, settings=settings)
    if await _compose_direct_draft(state, settings=settings, primary_llm_client=primary_llm_client):
        VerifierAgent().verify(state)
        SafetyAgent().check(state)
        ResponseAgent().render(state)
        return state
    await RagAgent(rag_client or FakeRagServerClient()).run(state)
    policy = _apply_rag_answer_policy(state)
    if policy.should_use_retrieved_contexts:
        await GroundedAnswerAgent(settings=settings, primary_llm_client=primary_llm_client).run(state)
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
    if session_context_service is not None:
        previous_context = None
        if not session_context_service.clear_conflicted_context(resolved_session_id, query):
            previous_context = session_context_service.get_context(resolved_session_id)
        if previous_context is not None:
            state.session_context = previous_context.model_dump(mode="json")
            state.normalized_query = merge_session_slots(query, previous_context)
    route_override = await _maybe_route_intent_with_model(state, settings=settings, session_context=state.session_context)
    route_override = _guard_disease_route_override(route_override)
    SupervisorAgent().route(state, route_override=route_override)
    if route_override is None:
        record_shadow_route(state, settings=settings)
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
        await RagAgent(rag_client or FakeRagServerClient()).run(state)
        policy = _apply_rag_answer_policy(state)
        if policy.should_use_retrieved_contexts:
            await GroundedAnswerAgent(settings=settings, primary_llm_client=primary_llm_client).run(state)
        if unsafe_draft_for_test is not None:
            state.draft_answer = unsafe_draft_for_test
        VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


def merge_session_slots(query: str, context: SessionContextData) -> str:
    parts = [query]
    if isinstance(context.last_understanding, dict):
        summary = context.last_understanding.get("case_summary")
        if summary:
            parts.append(str(summary))
        for key in ("observed_signs", "context_factors"):
            value = context.last_understanding.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value if str(item).strip())
    fields = context.confirmed_case_fields or {}
    for value in fields.values():
        if isinstance(value, list):
            parts.extend(str(item) for item in value if str(item).strip())
        elif value not in (None, "", {}, []):
            parts.append(str(value))
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


async def _compose_direct_draft(
    state: MultiAgentState,
    *,
    settings: Settings | None = None,
    primary_llm_client: Any | None = None,
) -> bool:
    if state.intent not in {"assistant_intro", "out_of_scope", "measurement_analysis"}:
        return False

    app_settings = settings or Settings()
    if FeatureFlagService(app_settings).primary_llm_enabled:
        await DirectAnswerAgent(settings=app_settings, primary_llm_client=primary_llm_client).run(state)
        return True

    state.draft_answer = fallback_direct_answer(state.intent)
    state.evidence_status = "empty"
    return True


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
    if result.selected_model != "local_small":
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


async def _maybe_route_intent_with_model(
    state: MultiAgentState,
    *,
    settings: Settings | None = None,
    session_context: dict[str, Any] | None = None,
) -> IntentRoutingResult | None:
    app_settings = settings or Settings()
    if not FeatureFlagService(app_settings).model_router_enabled:
        return None
    return await route_intent_with_model(
        state.normalized_query or state.user_query,
        settings=app_settings,
        session_context=session_context or state.session_context,
    )


def _guard_disease_route_override(route: IntentRoutingResult | None) -> IntentRoutingResult | None:
    if route is None or route.intent == "disease_consultation":
        return route
    guarded = route.model_copy(deep=True)
    guarded.intent = "disease_consultation"
    guarded.reason = "disease graph/context requires disease consultation"
    guarded.should_use_rag = True
    guarded.fallback_used = True
    guarded.fallback_reason = "disease_graph_guardrail"
    return guarded


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
    value: dict[str, object] = {}
    understanding = _last_disease_understanding(state)
    if isinstance(understanding, dict):
        for field in ("case_summary", "species", "observed_signs", "context_factors", "explicit_user_facts"):
            item = understanding.get(field)
            if item not in (None, "", [], {}):
                value[field] = item
    if not value:
        value["case_summary"] = state.normalized_query or state.user_query
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
    disease_assessment = state.disease_assessment or {}
    confirmed_case_fields = _confirmed_case_fields(state)

    session_context_service.save_context(
        SessionContextData(
            session_id=state.session_id,
            last_intent="disease_consultation",
            last_species=_understanding_species(state),
            last_symptoms=_understanding_signs(state),
            pending_slots=[],
            confirmed_case_fields=confirmed_case_fields,
            pending_questions=[],
            answered_questions=list(confirmed_case_fields.keys()),
            last_understanding=_last_disease_understanding(state),
            evidence_refs=_rag_evidence_refs(state),
            slot_sources={},
            risk_context_status=str(disease_assessment.get("status") or "active"),
        )
    )


def _confirmed_case_fields(state: MultiAgentState) -> dict[str, object]:
    confirmed: dict[str, object] = {}
    understanding = _last_disease_understanding(state)
    if isinstance(understanding, dict):
        for field in ("case_summary", "species", "observed_signs", "context_factors", "explicit_user_facts"):
            value = understanding.get(field)
            if value not in (None, "", [], {}):
                confirmed[field] = value
    return confirmed


def _understanding_species(state: MultiAgentState) -> str | None:
    understanding = _last_disease_understanding(state)
    if isinstance(understanding, dict) and understanding.get("species"):
        return str(understanding["species"])
    return None


def _understanding_signs(state: MultiAgentState) -> list[str]:
    understanding = _last_disease_understanding(state)
    if isinstance(understanding, dict) and isinstance(understanding.get("observed_signs"), list):
        return [str(item) for item in understanding["observed_signs"] if str(item).strip()]
    return []


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
