from __future__ import annotations

from uuid import uuid4

from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.measurement_agent import MeasurementAgent
from backend.app.agent.rag_agent import RagAgent
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
from backend.app.model.router import ModelRouteRequest, ModelRouter, ModelTaskType
from backend.app.schemas.measurement import MeasurementInput
from backend.app.schemas.rag_server import RagSearchResult
from backend.app.services.feature_flag_service import FeatureFlagService
from backend.app.services.session_context_service import SessionContextData, SessionContextService


async def run_general_qa_graph(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> MultiAgentState:
    state = MultiAgentState(session_id=session_id or _new_session_id(), user_query=query)
    SupervisorAgent().route(state)
    record_shadow_route(state, settings=settings)
    await RagAgent(rag_client or FakeRagServerClient()).run(state)
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
    unsafe_draft_for_test: str | None = None,
    settings: Settings | None = None,
) -> MultiAgentState:
    resolved_session_id = session_id or _new_session_id()
    state = MultiAgentState(session_id=resolved_session_id, user_query=query)
    SupervisorAgent().route(state)
    record_shadow_route(state, settings=settings)
    if session_context_service is not None:
        previous_context = None
        if not session_context_service.clear_conflicted_context(resolved_session_id, query):
            previous_context = session_context_service.get_context(resolved_session_id)
        if previous_context is not None:
            state.normalized_query = merge_session_slots(query, previous_context)
    DiseaseAgent().run(state)
    if session_context_service is not None:
        _save_disease_context(session_context_service, state)
    if state.rag_query:
        disease_draft = state.draft_answer or ""
        await RagAgent(rag_client or FakeRagServerClient()).run(state)
        _compose_rag_draft(state, prefix=disease_draft)
        if unsafe_draft_for_test is not None:
            state.draft_answer = unsafe_draft_for_test
        VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


def merge_session_slots(query: str, context: SessionContextData) -> str:
    parts = [query]
    if context.last_species:
        parts.append(_species_label(context.last_species))
    for symptom in context.last_symptoms:
        parts.append(_symptom_label(symptom))
    return " ".join(part for part in parts if part)


async def run_measurement_graph(
    measurement: MeasurementInput,
    *,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> MultiAgentState:
    state = MultiAgentState(
        session_id=session_id or _new_session_id(),
        user_query=f"body measurement analysis for {measurement.animal_id}",
    )
    SupervisorAgent().route(state)
    record_shadow_route(state, settings=settings)
    MeasurementAgent().run(state, measurement)
    VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


def _compose_rag_draft(state: MultiAgentState, *, prefix: str | None = None) -> None:
    rag_result = state.tool_results.get("livestock_rag_search")
    if isinstance(rag_result, dict):
        evidence_answer = AnswerGenerator().compose_with_citations(RagSearchResult.model_validate(rag_result))
        state.draft_answer = f"{prefix}\n\n{evidence_answer}" if prefix else evidence_answer


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


def _model_task_type(state: MultiAgentState) -> ModelTaskType:
    if state.intent == "measurement_analysis":
        return "measurement_analysis"
    return "final_answer"


def _requires_final_answer(state: MultiAgentState) -> bool:
    return state.intent in {"general_qa", "disease_consultation", "out_of_scope"}


def _new_session_id() -> str:
    return f"s_{uuid4().hex}"


def _save_disease_context(session_context_service: SessionContextService, state: MultiAgentState) -> None:
    slots = state.extracted_slots
    disease_assessment = state.disease_assessment or {}
    pending_slots = list(disease_assessment.get("missing_info") or [])
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
            slot_sources=slot_sources,
            risk_context_status="incomplete" if pending_slots else str(disease_assessment.get("risk_level") or "complete"),
        )
    )


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
