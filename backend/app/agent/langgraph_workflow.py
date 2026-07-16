from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from backend.app.agent.direct_answer_agent import DirectAnswerAgent, fallback_direct_answer
from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.grounded_answer_agent import GroundedAnswerAgent
from backend.app.agent.measurement_agent import MeasurementAgent
from backend.app.agent.rag_agent import RagAgent
from backend.app.agent.rag_answer_policy import (
    NO_ANSWER_TEXT,
    SAFETY_REFUSAL_TEXT,
    classify_rag_answer_policy,
)
from backend.app.agent.response_agent import ResponseAgent
from backend.app.agent.router import IntentRouter
from backend.app.agent.safety_agent import SafetyAgent
from backend.app.agent.safety_precheck import SafetyPrecheck
from backend.app.agent.state import MultiAgentState
from backend.app.agent.supervisor import ACTIVE_AGENT_BY_INTENT, SupervisorAgent
from backend.app.agent.verifier_agent import VerifierAgent
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.model.base import BaseModelClient
from backend.app.model.intent_router import IntentRoutingResult, route_intent_with_model
from backend.app.model.query_normalizer import normalize_query_with_router
from backend.app.model.router import ModelRouteRequest, ModelRouter
from backend.app.schemas.agent import AgentToolError, IntentType
from backend.app.schemas.measurement import MeasurementInput
from backend.app.services.feature_flag_service import FeatureFlagService
from backend.app.services.memory_service import (
    MemoryEvent,
    MemoryFact,
    MemoryService,
    build_measurement_memory_fact,
)
from backend.app.services.session_context_service import SessionContextData, SessionContextService


RAG_TOOL_NAME = "livestock_rag_search"
PLANNER_TOOL_NAME = "query_knowledge_hub"
MAX_TOOL_ATTEMPTS = 2


@dataclass
class AgentGraphRuntime:
    """Per-invocation dependencies kept outside the serializable graph state."""

    settings: Settings = field(default_factory=Settings)
    rag_client: RagServerClient = field(default_factory=FakeRagServerClient)
    session_context_service: SessionContextService | None = None
    memory_service: MemoryService | None = None
    query_normalizer_client: BaseModelClient | None = None
    intent_router_client: BaseModelClient | None = None
    intent_router: Callable[..., Awaitable[IntentRoutingResult]] | None = None
    primary_llm_client: Any | None = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    measurement: MeasurementInput | None = None
    forced_intent: IntentType | None = None
    animal_id: str | None = None
    unsafe_draft_for_test: str | None = None


def build_chat_graph():
    builder = StateGraph(MultiAgentState, context_schema=AgentGraphRuntime)
    builder.add_node("context", _context_node)
    builder.add_node("router", _router_node)
    builder.add_node("direct", _direct_node)
    builder.add_node("disease_prepare", _disease_prepare_node)
    builder.add_node("planner", _planner_node)
    builder.add_node("tool", _tool_node)
    builder.add_node("reasoning", _reasoning_node)
    builder.add_node("verifier", _verifier_node)
    builder.add_node("safety", _safety_node)
    builder.add_node("final", _final_node)

    builder.add_edge(START, "context")
    builder.add_edge("context", "router")
    builder.add_conditional_edges(
        "router",
        _chat_route,
        {
            "direct": "direct",
            "general": "planner",
            "disease": "disease_prepare",
        },
    )
    builder.add_edge("direct", "verifier")
    builder.add_edge("disease_prepare", "planner")
    builder.add_edge("planner", "tool")
    builder.add_conditional_edges(
        "tool",
        _after_tool_route,
        {"retry": "tool", "reasoning": "reasoning"},
    )
    builder.add_edge("reasoning", "verifier")
    builder.add_edge("verifier", "safety")
    builder.add_edge("safety", "final")
    builder.add_edge("final", END)
    return builder.compile()


def build_measurement_graph():
    builder = StateGraph(MultiAgentState, context_schema=AgentGraphRuntime)
    builder.add_node("context", _context_node)
    builder.add_node("router", _router_node)
    builder.add_node("measurement", _measurement_node)
    builder.add_node("verifier", _verifier_node)
    builder.add_node("safety", _safety_node)
    builder.add_node("final", _final_node)

    builder.add_edge(START, "context")
    builder.add_edge("context", "router")
    builder.add_edge("router", "measurement")
    builder.add_edge("measurement", "verifier")
    builder.add_edge("verifier", "safety")
    builder.add_edge("safety", "final")
    builder.add_edge("final", END)
    return builder.compile()


async def _context_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    session_data = dict(state.session_context)
    if context.conversation_history:
        session_data["conversation_history"] = list(context.conversation_history)

    service = context.session_context_service
    if service is not None:
        previous = None
        if not service.clear_conflicted_context(state.session_id, state.user_query):
            previous = service.get_context(state.session_id)
        if previous is not None:
            persisted = previous.model_dump(mode="json")
            persisted.update(session_data)
            session_data = persisted

    state.session_context = session_data
    return _dump(state)


async def _router_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    await _maybe_normalize_query(state, context)

    route_override = None
    if context.forced_intent != "measurement_analysis" and context.measurement is None:
        route_override = await _maybe_route_intent_with_model(state, context)
    SupervisorAgent().route(state, route_override=route_override)

    forced_intent = context.forced_intent
    if context.measurement is not None:
        forced_intent = "measurement_analysis"
    elif forced_intent is None and _should_continue_disease_context(state):
        forced_intent = "disease_consultation"
    if forced_intent is not None:
        _force_intent(state, forced_intent)

    if context.forced_intent == "measurement_analysis" or context.measurement is not None:
        _record_model_router_shadow(state, context.settings)
    return _dump(state)


async def _direct_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    if FeatureFlagService(context.settings).primary_llm_enabled:
        await DirectAnswerAgent(
            settings=context.settings,
            primary_llm_client=context.primary_llm_client,
        ).run(state)
    else:
        state.draft_answer = fallback_direct_answer(state.intent)
        state.evidence_status = "empty"
    return _dump(state)


async def _disease_prepare_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    previous = _session_context_from_state(state)
    if previous is not None:
        state.normalized_query = merge_session_slots(state.normalized_query or state.user_query, previous)

    await asyncio.to_thread(
        DiseaseAgent(
            settings=context.settings,
            primary_llm_client=context.primary_llm_client,
        ).run,
        state,
    )
    if context.session_context_service is not None:
        _save_disease_context(context.session_context_service, state)
    _maybe_write_disease_memory(state, context)
    return _dump(state)


def _planner_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    if not state.tool_plan:
        state.tool_plan = [
            {
                "tool": PLANNER_TOOL_NAME,
                "arguments": {
                    "query": (state.rag_query or state.normalized_query or state.user_query).strip(),
                    "top_k": 4,
                },
            }
        ]
    return _dump(state)


async def _tool_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    valid, error_code = validate_tool_plan(state.tool_plan)
    if not valid:
        _record_invalid_plan(state, error_code or "PLANNER_TOOL_NOT_ALLOWED")
        return _dump(state)

    if state.tool_attempt:
        _prepare_rag_retry(state)
    arguments = state.tool_plan[0]["arguments"]
    state.rag_query = str(arguments["query"]).strip()
    state.tool_attempt += 1
    await RagAgent(
        context.rag_client,
        top_k=int(arguments.get("top_k", 4)),
    ).run(state)
    return _dump(state)


async def _reasoning_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    policy = _apply_rag_answer_policy(state)
    if policy.should_use_retrieved_contexts:
        await GroundedAnswerAgent(
            settings=context.settings,
            primary_llm_client=context.primary_llm_client,
        ).run(state)
    if state.intent == "disease_consultation" and context.unsafe_draft_for_test is not None:
        state.draft_answer = context.unsafe_draft_for_test
    return _dump(state)


def _measurement_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    if context.measurement is None:
        state.draft_answer = fallback_direct_answer("measurement_analysis")
        state.evidence_status = "empty"
        state.errors.append(
            AgentToolError(
                tool_name="measurement_agent",
                error_code="MEASUREMENT_INPUT_MISSING",
                message="structured measurement input is required",
            )
        )
        return _dump(state)

    MeasurementAgent(settings=context.settings).run(state, context.measurement)
    _maybe_write_measurement_memory(state, context.measurement, context)
    return _dump(state)


def _verifier_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    VerifierAgent().verify(state)
    return _dump(state)


def _safety_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    SafetyAgent().check(state)
    return _dump(state)


def _final_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    ResponseAgent().render(state)
    return _dump(state)


def _chat_route(raw_state: MultiAgentState | dict[str, Any]) -> str:
    intent = _state(raw_state).intent
    if intent == "general_qa":
        return "general"
    if intent == "disease_consultation":
        return "disease"
    return "direct"


def _after_tool_route(raw_state: MultiAgentState | dict[str, Any]) -> str:
    state = _state(raw_state)
    validation = state.tool_results.get("tool_plan_validation")
    if isinstance(validation, dict) and not validation.get("valid", True):
        return "reasoning"
    if state.evidence_status == "error" and state.tool_attempt < MAX_TOOL_ATTEMPTS:
        return "retry"
    return "reasoning"


def validate_tool_plan(plan: list[dict[str, Any]]) -> tuple[bool, str | None]:
    if not plan:
        return False, "PLAN_MISSING"
    if len(plan) != 1:
        return False, "PLANNER_TOOL_NOT_ALLOWED"
    item = plan[0]
    if not isinstance(item, dict) or item.get("tool") != PLANNER_TOOL_NAME:
        return False, "PLANNER_TOOL_NOT_ALLOWED"
    arguments = item.get("arguments")
    if not isinstance(arguments, dict):
        return False, "PLANNER_TOOL_ARGUMENTS_INVALID"
    if not isinstance(arguments.get("query"), str) or not arguments["query"].strip():
        return False, "PLANNER_TOOL_ARGUMENTS_INVALID"
    top_k = arguments.get("top_k", 4)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
        return False, "PLANNER_TOOL_ARGUMENTS_INVALID"
    return True, None


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
    for value in (context.confirmed_case_fields or {}).values():
        if isinstance(value, list):
            parts.extend(str(item) for item in value if str(item).strip())
        elif value not in (None, "", {}, []):
            parts.append(str(value))
    return " ".join(part for part in parts if part)


async def _maybe_normalize_query(state: MultiAgentState, context: AgentGraphRuntime) -> None:
    if not FeatureFlagService(context.settings).model_router_enabled:
        state.normalized_query = state.normalized_query or state.user_query.strip()
        return
    result = await normalize_query_with_router(
        state.user_query,
        settings=context.settings,
        client=context.query_normalizer_client,
    )
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
        state.tool_results.setdefault("model_fallbacks", []).append(
            {
                "component": "query_normalizer",
                "selected_model": result.selected_model,
                "fallback_reason": result.fallback_reason,
                "route_mode": result.route_mode,
            }
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
    context: AgentGraphRuntime,
) -> IntentRoutingResult | None:
    if not FeatureFlagService(context.settings).model_router_enabled:
        return None
    router = context.intent_router or route_intent_with_model
    return await router(
        state.normalized_query or state.user_query,
        settings=context.settings,
        client=context.intent_router_client,
        session_context=state.session_context,
    )


def _force_intent(state: MultiAgentState, intent: IntentType) -> None:
    reason = "runtime/context requires this workflow branch"
    model_route = state.tool_results.get("intent_router_model")
    if isinstance(model_route, dict) and model_route.get("intent") != intent:
        fallback_reason = (
            "disease_graph_guardrail"
            if intent == "disease_consultation"
            else f"{intent}_graph_guardrail"
        )
        model_route.update(
            {
                "intent": intent,
                "reason": reason,
                "should_use_rag": intent in {"general_qa", "disease_consultation"},
                "fallback_used": True,
                "fallback_reason": fallback_reason,
            }
        )
    state.intent = intent
    state.route_reason = reason
    state.active_agent = ACTIVE_AGENT_BY_INTENT[intent]
    supervisor = state.tool_results.get("supervisor")
    if isinstance(supervisor, dict):
        supervisor.update({"intent": intent, "reason": reason, "route_source": "forced"})
    if state.agent_trace and state.agent_trace[-1].get("node") == "supervisor":
        state.agent_trace[-1].update(
            {
                "intent": intent,
                "active_agent": ACTIVE_AGENT_BY_INTENT[intent],
                "route_reason": reason,
                "route_source": "forced",
            }
        )


def _should_continue_disease_context(state: MultiAgentState) -> bool:
    if state.session_context.get("last_intent") != "disease_consultation":
        return False
    router = IntentRouter()
    route = router.route(state.user_query)
    if route.intent == "disease_consultation":
        return True
    if router._contains_any(state.user_query, router.disease_keywords):
        return True
    if re.search(r"\[[a-z_]+\s*=", state.user_query, flags=re.IGNORECASE):
        return True
    normalized = state.user_query.strip().lower()
    markers = {
        "那怎么办",
        "接下来",
        "然后呢",
        "还是这样",
        "这种情况",
        "继续",
        "体温",
        "天了",
        "一只",
        "what next",
        "what should i do",
        "still sick",
        "and then",
    }
    return any(marker in normalized for marker in markers)


def _record_model_router_shadow(state: MultiAgentState, settings: Settings) -> None:
    if not FeatureFlagService(settings).model_router_enabled:
        return
    safety = SafetyPrecheck().classify(state.normalized_query or state.user_query)
    request = ModelRouteRequest(
        task_type="measurement_analysis",
        safety_level=safety.level,
        requires_final_answer=False,
        user_query=state.normalized_query or state.user_query,
        metadata={"intent": state.intent or "unknown"},
    )
    decision = ModelRouter(settings).route(request)
    state.tool_results["model_router_shadow"] = {
        "safety_precheck": safety.model_dump(),
        "route_request": request.model_dump(),
        "route_decision": decision.model_dump(),
    }
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


def _apply_rag_answer_policy(state: MultiAgentState):
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


def _record_invalid_plan(state: MultiAgentState, error_code: str) -> None:
    message = (
        "planner tool arguments are invalid"
        if error_code == "PLANNER_TOOL_ARGUMENTS_INVALID"
        else "planner requested a tool outside the allowlist"
    )
    state.evidence_status = "error"
    state.tool_results["tool_plan_validation"] = {
        "valid": False,
        "error_code": error_code,
    }
    state.tool_results[RAG_TOOL_NAME] = {
        "query": state.rag_query or state.normalized_query or state.user_query,
        "status": "error",
        "hits": [],
        "citations": [],
        "mapping_warnings": [],
        "error_code": error_code,
        "error_message": message,
    }
    state.errors.append(
        AgentToolError(
            tool_name="planner",
            error_code=error_code,
            message=message,
        )
    )


def _prepare_rag_retry(state: MultiAgentState) -> None:
    previous = state.tool_results.get(RAG_TOOL_NAME)
    if isinstance(previous, dict):
        state.tool_results.setdefault("rag_retry_history", []).append(previous)
    state.errors = [error for error in state.errors if error.tool_name != "rag_agent"]
    state.retrieved_contexts.clear()
    state.evidence_status = None


def _session_context_from_state(state: MultiAgentState) -> SessionContextData | None:
    if state.session_context.get("last_intent") != "disease_consultation":
        return None
    try:
        return SessionContextData.model_validate(state.session_context)
    except Exception:
        return None


def _maybe_write_measurement_memory(
    state: MultiAgentState,
    measurement: MeasurementInput,
    context: AgentGraphRuntime,
) -> None:
    if not FeatureFlagService(context.settings).memory_write_enabled or context.memory_service is None:
        return
    event = context.memory_service.maybe_write_memory(
        build_measurement_memory_fact(
            measurement,
            source="user_confirmed",
            metadata={"session_id": state.session_id, "agent": "measurement_agent"},
        )
    )
    _record_memory_write(state, event)


def _maybe_write_disease_memory(state: MultiAgentState, context: AgentGraphRuntime) -> None:
    if (
        not context.animal_id
        or not FeatureFlagService(context.settings).memory_write_enabled
        or context.memory_service is None
    ):
        return
    understanding = _last_disease_understanding(state)
    value: dict[str, object] = {}
    if understanding is not None:
        for key in ("case_summary", "species", "observed_signs", "context_factors", "explicit_user_facts"):
            item = understanding.get(key)
            if item not in (None, "", [], {}):
                value[key] = item
    if not value:
        value["case_summary"] = state.normalized_query or state.user_query
    event = context.memory_service.maybe_write_memory(
        MemoryFact(
            subject_type="animal",
            subject_id=context.animal_id,
            fact_type="user_confirmed_observation",
            value=value,
            source="user_confirmed",
            metadata={"session_id": state.session_id, "agent": "disease_agent"},
        )
    )
    _record_memory_write(state, event)


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


def _save_disease_context(service: SessionContextService, state: MultiAgentState) -> None:
    understanding = _last_disease_understanding(state)
    confirmed: dict[str, object] = {}
    if understanding is not None:
        for key in ("case_summary", "species", "observed_signs", "context_factors", "explicit_user_facts"):
            value = understanding.get(key)
            if value not in (None, "", [], {}):
                confirmed[key] = value
    service.save_context(
        SessionContextData(
            session_id=state.session_id,
            last_intent="disease_consultation",
            last_species=str(understanding.get("species")) if understanding and understanding.get("species") else None,
            last_symptoms=[
                str(item)
                for item in ((understanding or {}).get("observed_signs") or [])
                if str(item).strip()
            ],
            pending_slots=[],
            confirmed_case_fields=confirmed,
            pending_questions=[],
            answered_questions=list(confirmed),
            last_understanding=understanding,
            evidence_refs=[],
            slot_sources={},
            risk_context_status=str((state.disease_assessment or {}).get("status") or "active"),
        )
    )


def _last_disease_understanding(state: MultiAgentState) -> dict[str, Any] | None:
    for key in ("disease_understanding", "disease_understanding_shadow"):
        record = state.tool_results.get(key)
        if isinstance(record, dict) and isinstance(record.get("understanding"), dict):
            return record["understanding"]
    return None


def _state(value: MultiAgentState | dict[str, Any]) -> MultiAgentState:
    if isinstance(value, MultiAgentState):
        return value.model_copy(deep=True)
    return MultiAgentState.model_validate(value)


def _context(runtime: Runtime[AgentGraphRuntime]) -> AgentGraphRuntime:
    value = getattr(runtime, "context", None)
    if not isinstance(value, AgentGraphRuntime):
        raise RuntimeError("AgentGraphRuntime context is required")
    return value


def _dump(state: MultiAgentState) -> dict[str, Any]:
    return state.model_dump(mode="python")
