from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore

from backend.app.agent.agentic_retrieval import AgenticRetrievalOrchestrator
from backend.app.agent.direct_answer_agent import (
    DirectAnswerAgent,
    fallback_direct_answer,
)
from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.grounded_answer_agent import GroundedAnswerAgent
from backend.app.agent.measurement_agent import MeasurementAgent
from backend.app.agent.memory_tools import MemoryType, search_memory, write_memory
from backend.app.agent.plan_executor import (
    ActionOutcome,
    ExecutionHandlers,
    ExecutorAgent,
)
from backend.app.agent.plan_verifier import PlanVerifier
from backend.app.agent.query_constraints import extract_query_constraints
from backend.app.agent.rag_answer_policy import (
    NO_ANSWER_TEXT,
    SAFETY_REFUSAL_TEXT,
    classify_rag_answer_policy,
)
from backend.app.agent.replan_agent import ReplanAgent
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
from backend.app.model.router import ModelRouter, ModelRouteRequest
from backend.app.schemas.agent import AgentToolError, IntentType, RetrievedContext
from backend.app.schemas.measurement import MeasurementInput
from backend.app.schemas.planning import ExecutionFailure, PlanStep
from backend.app.schemas.rag_server import RagSearchResult
from backend.app.schemas.retrieval import (
    AgenticRetrievalState,
    RetrievalQuery,
    RetrievalQuerySource,
)
from backend.app.services.feature_flag_service import FeatureFlagService
from backend.app.services.memory_service import (
    MemoryEvent,
    MemoryFact,
    MemoryService,
    MemorySource,
    build_measurement_memory_fact,
)
from backend.app.services.session_context_service import (
    SessionContextData,
    SessionContextService,
)

RAG_TOOL_NAME = "livestock_rag_search"
PLANNER_TOOL_NAME = "query_knowledge_hub"


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
    user_id: str | None = None
    animal_id: str | None = None
    animal_profile: dict[str, Any] | None = None
    memory_scope_authoritative: bool = False
    unsafe_draft_for_test: str | None = None


def build_chat_graph(
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    store: BaseStore | None = None,
    interrupt_after: list[str] | None = None,
):
    builder = StateGraph(MultiAgentState, context_schema=AgentGraphRuntime)
    builder.add_node("context", _context_node)
    builder.add_node("memory_search", _memory_search_node)
    builder.add_node("router", _router_node)
    builder.add_node("direct", _direct_node)
    builder.add_node("planner", _planner_node)
    builder.add_node("executor", _executor_node)
    builder.add_node("plan_verifier", _plan_verifier_node)
    builder.add_node("replan", _replan_node)
    builder.add_node("verifier", _verifier_node)
    builder.add_node("safety", _safety_node)
    builder.add_node("final", _final_node)
    builder.add_node("memory_write", _memory_write_node)

    builder.add_edge(START, "context")
    builder.add_edge("context", "memory_search")
    builder.add_edge("memory_search", "router")
    builder.add_conditional_edges(
        "router",
        _chat_route,
        {
            "direct": "direct",
            "general": "planner",
            "disease": "planner",
        },
    )
    builder.add_edge("direct", "verifier")
    builder.add_edge("planner", "executor")
    builder.add_conditional_edges(
        "plan_verifier",
        _after_plan_verification,
        {
            "next": "executor",
            "replan": "replan",
            "goal": "verifier",
            "terminal": "verifier",
        },
    )
    builder.add_edge("executor", "plan_verifier")
    builder.add_conditional_edges(
        "replan",
        _after_replan,
        {"executor": "executor", "verifier": "verifier"},
    )
    builder.add_edge("verifier", "safety")
    builder.add_edge("safety", "final")
    builder.add_edge("final", "memory_write")
    builder.add_edge("memory_write", END)
    return builder.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_after=interrupt_after,
    )


async def resume_chat_graph(
    graph: CompiledStateGraph,
    *,
    runtime: AgentGraphRuntime,
    config: dict[str, Any],
) -> MultiAgentState:
    """Resume an interrupted chat run from its persisted checkpoint."""

    raw = await graph.ainvoke(None, context=runtime, config=config)
    return MultiAgentState.model_validate(raw)


def build_measurement_graph(
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    store: BaseStore | None = None,
):
    builder = StateGraph(MultiAgentState, context_schema=AgentGraphRuntime)
    builder.add_node("context", _context_node)
    builder.add_node("memory_search", _memory_search_node)
    builder.add_node("router", _router_node)
    builder.add_node("measurement", _measurement_node)
    builder.add_node("verifier", _verifier_node)
    builder.add_node("safety", _safety_node)
    builder.add_node("final", _final_node)
    builder.add_node("memory_write", _memory_write_node)

    builder.add_edge(START, "context")
    builder.add_edge("context", "memory_search")
    builder.add_edge("memory_search", "router")
    builder.add_edge("router", "measurement")
    builder.add_edge("measurement", "verifier")
    builder.add_edge("verifier", "safety")
    builder.add_edge("safety", "final")
    builder.add_edge("final", "memory_write")
    builder.add_edge("memory_write", END)
    return builder.compile(checkpointer=checkpointer, store=store)


async def _context_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    if state.turn_reset_required:
        _reset_transient_turn_state(state)
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


def _reset_transient_turn_state(state: MultiAgentState) -> None:
    state.turn_reset_required = False
    state.normalized_query = None
    state.intent = None
    state.risk_level = None
    state.route_reason = None
    state.active_agent = None
    state.extracted_slots = {}
    state.rag_query = None
    state.retrieved_contexts = []
    state.evidence_status = None
    state.agentic_retrieval = None
    state.disease_assessment = None
    state.measurement_report = None
    state.draft_answer = None
    state.verification_result = None
    state.safety_result = None
    state.final_answer = None
    state.task_plan = None
    state.current_step_id = None
    state.step_results = []
    state.execution_failure = None
    state.execution_count = 0
    state.plan_verification = None
    state.replan_count = 0
    state.replan_history = []
    state.tool_plan = []
    state.tool_attempt = 0
    state.tool_results = {}
    state.errors = []
    state.agent_trace = []


async def _memory_search_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    state.session_context.pop("long_term_memory", None)
    if not _memory_ready(runtime, read=True):
        return _dump(state)

    store = runtime.store
    if store is None:
        return _dump(state)
    try:
        items = await search_memory(
            store,
            user_id=context.user_id or "",
            subject_type="animal",
            subject_id=context.animal_id or "",
            limit=5,
        )
    except Exception:
        state.tool_results["search_memory"] = {
            "status": "error",
            "error_code": "MEMORY_SEARCH_FAILED",
            "count": 0,
        }
        _record_memory_trace(state, "search_memory", "error", 0)
        return _dump(state)

    records = [item.model_dump(mode="json") for item in items]
    state.session_context["long_term_memory"] = records
    state.tool_results["search_memory"] = {
        "status": "success",
        "count": len(records),
        "records": records,
    }
    _record_memory_trace(state, "search_memory", "success", len(records))
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


async def _planner_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    if state.tool_plan:
        valid, error_code = validate_tool_plan(state.tool_plan)
        if not valid:
            _record_invalid_plan(state, error_code or "PLANNER_TOOL_NOT_ALLOWED")
            return _dump(state)
    await SupervisorAgent().plan(
        state,
        settings=context.settings,
        primary_llm_client=context.primary_llm_client,
    )
    return _dump(state)


async def _executor_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    handlers = ExecutionHandlers(
        understand_disease=lambda current, step, key: _execute_disease_understanding(
            current, step, key, context
        ),
        query_knowledge_hub=lambda current, step, key: _execute_knowledge_query(
            current, step, key, context
        ),
        compose_grounded_answer=lambda current, step, key: _execute_grounded_answer(
            current, step, key, context
        ),
        safe_fallback=_execute_safe_fallback,
    )
    await ExecutorAgent(handlers).execute_next(state)
    return _dump(state)


async def _execute_disease_understanding(
    state: MultiAgentState,
    step: PlanStep,
    operation_key: str,
    context: AgentGraphRuntime,
) -> ActionOutcome:
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
    assessment = state.disease_assessment if isinstance(state.disease_assessment, dict) else {}
    gaps = [str(item) for item in assessment.get("information_gaps") or [] if str(item).strip()]
    assessment["follow_up_questions"] = [_gap_to_question(item, state.user_query) for item in gaps][:3]
    state.disease_assessment = assessment
    if not assessment:
        return ActionOutcome.failure(
            "DISEASE_UNDERSTANDING_MISSING",
            "disease understanding did not produce an assessment",
            retryable=True,
        )
    return ActionOutcome.success("disease_assessment")


async def _execute_knowledge_query(
    state: MultiAgentState,
    step: PlanStep,
    operation_key: str,
    context: AgentGraphRuntime,
) -> ActionOutcome:
    started_at = time.perf_counter()
    query_source = cast(RetrievalQuerySource, step.arguments["query_source"])
    query = getattr(state, query_source, None)
    if not isinstance(query, str) or not query.strip():
        return ActionOutcome.failure(
            "TRUSTED_QUERY_MISSING",
            f"trusted query source is empty: {query_source}",
            retryable=False,
        )
    if state.tool_attempt:
        _prepare_rag_retry(state)
    state.rag_query = query.strip()
    state.tool_attempt += 1
    policy = _apply_rag_answer_policy(state)
    if policy.force_no_answer or policy.force_safety_refusal:
        termination_code = "SAFETY_REFUSAL" if policy.force_safety_refusal else "POLICY_NO_ANSWER"
        state.agentic_retrieval = _blocked_retrieval_state(
            state.rag_query,
            query_source=query_source,
            termination_code=termination_code,
        )
        result = RagSearchResult(query=state.rag_query, status="low_confidence")
        state.tool_results[RAG_TOOL_NAME] = result.model_dump(mode="json")
        state.evidence_status = result.status
        _replace_retrieved_contexts(state, result)
        _record_agentic_retrieval_trace(
            state,
            query=state.rag_query,
            latency_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
        )
        return ActionOutcome.success(RAG_TOOL_NAME)
    if context.rag_client is None:
        return ActionOutcome.failure(
            "RAG_CLIENT_MISSING",
            "RAG client is not configured",
            retryable=False,
        )
    outcome = await AgenticRetrievalOrchestrator(
        context.rag_client,
        top_k=int(step.arguments["top_k"]),
        settings=context.settings,
        primary_llm_client=context.primary_llm_client,
    ).run(
        original_query=state.rag_query,
        query_source=query_source,
        request_id=state.request_id,
        operation_prefix=operation_key.rsplit(":", 1)[0],
    )
    state.agentic_retrieval = outcome.state
    state.tool_results[RAG_TOOL_NAME] = outcome.result.model_dump(mode="json")
    state.evidence_status = outcome.result.status
    _replace_retrieved_contexts(state, outcome.result)
    _record_agentic_retrieval_trace(
        state,
        query=state.rag_query,
        latency_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
    )
    result = state.tool_results[RAG_TOOL_NAME]
    if state.evidence_status == "error":
        first_attempt_error = next(
            (
                attempt.error_code
                for attempt in outcome.state.attempts
                if attempt.status == "error" and attempt.error_code
            ),
            None,
        )
        error_code = (
            str(first_attempt_error or result.get("error_code") or "RAG_EXECUTION_FAILED")
            if isinstance(result, dict)
            else "RAG_EXECUTION_FAILED"
        )
        if isinstance(result, dict):
            result["error_code"] = error_code
        error_message = (
            str(result.get("error_message") or "RAG execution failed")
            if isinstance(result, dict)
            else "RAG execution failed"
        )
        state.errors.append(
            AgentToolError(
                tool_name="rag_agent",
                error_code=error_code,
                message=error_message,
            )
        )
        return ActionOutcome.failure(
            error_code,
            error_message,
            retryable=_retryable_rag_error(error_code),
        )
    return ActionOutcome.success(RAG_TOOL_NAME)


async def _execute_grounded_answer(
    state: MultiAgentState,
    step: PlanStep,
    operation_key: str,
    context: AgentGraphRuntime,
) -> ActionOutcome:
    policy = _apply_rag_answer_policy(state)
    if policy.should_use_retrieved_contexts:
        await GroundedAnswerAgent(
            settings=context.settings,
            primary_llm_client=context.primary_llm_client,
        ).run(state)
    if state.intent == "disease_consultation" and context.unsafe_draft_for_test is not None:
        state.draft_answer = context.unsafe_draft_for_test
    if not state.draft_answer:
        return ActionOutcome.failure(
            "REASONING_DRAFT_MISSING",
            "grounded reasoning did not produce a draft answer",
            retryable=True,
        )
    return ActionOutcome.success("draft_answer")


def _execute_safe_fallback(
    state: MultiAgentState,
    step: PlanStep,
    operation_key: str,
) -> ActionOutcome:
    state.draft_answer = NO_ANSWER_TEXT
    state.evidence_status = "low_confidence"
    state.retrieved_contexts.clear()
    state.tool_results["plan_safe_fallback"] = {
        "status": "success",
        "reason_code": step.arguments.get("reason_code"),
    }
    return ActionOutcome.success("draft_answer")


def _plan_verifier_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    PlanVerifier().verify(state)
    return _dump(state)


def _replan_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    ReplanAgent().replan(state)
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
    context = _context(runtime)
    ResponseAgent().render(state)
    if state.intent == "disease_consultation":
        next_context = _build_disease_context(state)
        state.session_context = {
            **state.session_context,
            **next_context.model_dump(mode="json"),
        }
        if context.session_context_service is not None:
            context.session_context_service.save_context(next_context)
    return _dump(state)


async def _memory_write_node(
    raw_state: MultiAgentState | dict[str, Any],
    runtime: Runtime[AgentGraphRuntime],
) -> dict[str, Any]:
    state = _state(raw_state)
    context = _context(runtime)
    if state.intent == "disease_consultation":
        _maybe_write_disease_memory(state, context)
    if not _memory_ready(runtime, read=False):
        return _dump(state)

    writes: list[dict[str, Any]] = []
    if context.animal_profile:
        result = await _safe_write_memory(
            runtime,
            state,
            memory_type="animal_profile",
            content=dict(context.animal_profile),
            source="tool_result",
            operation_id=None,
            session_id=None,
        )
        writes.append(result)

    if state.intent == "disease_consultation":
        result = await _safe_write_memory(
            runtime,
            state,
            memory_type="consultation",
            content=_consultation_memory_content(state),
            source="user_confirmed",
            operation_id=state.request_id,
            session_id=state.session_id,
        )
        writes.append(result)
    elif state.intent == "measurement_analysis" and context.measurement is not None:
        content: dict[str, Any] = {
            "current": {
                key: value
                for key, value in context.measurement.current.model_dump().items()
                if value is not None
            }
        }
        if context.measurement.age_month is not None:
            content["age_month"] = context.measurement.age_month
        if context.measurement.confidence is not None:
            content["confidence"] = context.measurement.confidence
        result = await _safe_write_memory(
            runtime,
            state,
            memory_type="measurement",
            content=content,
            source="tool_result",
            operation_id=state.request_id,
            session_id=state.session_id,
        )
        writes.append(result)

    if writes:
        state.tool_results["write_memory"] = writes
        status = "error" if any(item.get("status") == "error" for item in writes) else "success"
        _record_memory_trace(state, "write_memory", status, len(writes))
    return _dump(state)


def _chat_route(raw_state: MultiAgentState | dict[str, Any]) -> str:
    intent = _state(raw_state).intent
    if intent == "general_qa":
        return "general"
    if intent == "disease_consultation":
        return "disease"
    return "direct"


def _after_plan_verification(raw_state: MultiAgentState | dict[str, Any]) -> str:
    state = _state(raw_state)
    if state.plan_verification is None:
        return "terminal"
    return state.plan_verification.decision


def _after_replan(raw_state: MultiAgentState | dict[str, Any]) -> str:
    state = _state(raw_state)
    if state.execution_failure is None and state.task_plan is not None:
        return "executor"
    return "verifier"


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
    raw_policy = classify_rag_answer_policy(state.user_query)
    policy = (
        raw_policy
        if raw_policy.force_no_answer or raw_policy.force_safety_refusal
        else classify_rag_answer_policy(state.normalized_query or state.user_query)
    )
    if policy.warning:
        state.tool_results["rag_answer_policy"] = policy.model_dump()
    if policy.force_no_answer:
        state.retrieved_contexts.clear()
        state.draft_answer = NO_ANSWER_TEXT
    elif policy.force_safety_refusal:
        state.retrieved_contexts.clear()
        state.draft_answer = SAFETY_REFUSAL_TEXT
    return policy


def _blocked_retrieval_state(
    query: str,
    *,
    query_source: RetrievalQuerySource,
    termination_code: str,
) -> AgenticRetrievalState:
    return AgenticRetrievalState(
        original_query=query,
        query_source=query_source,
        constraints=extract_query_constraints(query),
        decomposition_source="blocked",
        primary_queries=[
            RetrievalQuery(
                query_id="q_original",
                text=query,
                origin="original",
                purpose="request policy boundary",
            )
        ],
        final_status="blocked",
        termination_code=termination_code,
    )


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
    state.execution_failure = ExecutionFailure(
        category="invalid_plan",
        error_code=error_code,
        retryable=False,
        reason=message,
    )


def _retryable_rag_error(error_code: str) -> bool:
    permanent_codes = {
        "RAG_CLIENT_MISSING",
        "RAG_COLLECTION_NOT_FOUND",
        "RAG_SERVER_NOT_FOUND",
        "RAG_SERVER_PATH_MISSING",
        "TRUSTED_QUERY_MISSING",
    }
    return error_code not in permanent_codes


def _prepare_rag_retry(state: MultiAgentState) -> None:
    previous = state.tool_results.get(RAG_TOOL_NAME)
    if isinstance(previous, dict):
        state.tool_results.setdefault("rag_retry_history", []).append(previous)
    state.errors = [error for error in state.errors if error.tool_name != "rag_agent"]
    state.retrieved_contexts.clear()
    state.evidence_status = None
    state.agentic_retrieval = None


def _replace_retrieved_contexts(
    state: MultiAgentState,
    result: RagSearchResult,
) -> None:
    state.retrieved_contexts = [
        RetrievedContext(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            title=hit.document_title,
            content=hit.content,
            page=hit.page,
            section_title=hit.section_title,
            score=hit.score,
            source_type=hit.metadata.get("source_type"),
        )
        for hit in result.hits
    ]


def _record_agentic_retrieval_trace(
    state: MultiAgentState,
    *,
    query: str,
    latency_ms: int,
) -> None:
    retrieval = state.agentic_retrieval
    if retrieval is None:
        return
    final_grade = retrieval.grades[-1] if retrieval.grades else None
    error_code = next(
        (
            attempt.error_code
            for attempt in retrieval.attempts
            if attempt.status == "error" and attempt.error_code
        ),
        None,
    )
    state.agent_trace.append(
        {
            "node": "rag_agent",
            "mode": "agentic_retrieval",
            "status": state.evidence_status,
            "evidence_status": state.evidence_status,
            "query": query,
            "primary_query_count": len(retrieval.primary_queries),
            "secondary_used": retrieval.secondary_query is not None,
            "rag_call_count": retrieval.rag_call_count,
            "result_count": len(retrieval.selected_hit_keys),
            "grade_decision": final_grade.decision if final_grade is not None else None,
            "grade_reason_codes": list(final_grade.reason_codes) if final_grade is not None else [],
            "decomposition_source": retrieval.decomposition_source,
            "decomposition_fallback_reason": retrieval.decomposition_fallback_reason,
            "rewrite_source": retrieval.rewrite_source,
            "rewrite_fallback_reason": retrieval.rewrite_fallback_reason,
            "termination_code": retrieval.termination_code,
            "error_code": error_code,
            "latency_ms": latency_ms,
        }
    )


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


def _memory_ready(runtime: Runtime[AgentGraphRuntime], *, read: bool) -> bool:
    context = _context(runtime)
    flags = FeatureFlagService(context.settings)
    enabled = flags.memory_read_enabled if read else flags.memory_write_enabled
    return bool(
        enabled
        and context.memory_scope_authoritative
        and context.user_id
        and context.animal_id
        and runtime.store is not None
    )


async def _safe_write_memory(
    runtime: Runtime[AgentGraphRuntime],
    state: MultiAgentState,
    *,
    memory_type: MemoryType,
    content: dict[str, Any],
    source: MemorySource,
    operation_id: str | None,
    session_id: str | None,
) -> dict[str, Any]:
    context = _context(runtime)
    store = runtime.store
    if store is None:
        return {
            "status": "error",
            "error_code": "MEMORY_STORE_UNAVAILABLE",
            "memory_type": memory_type,
        }
    try:
        result = await write_memory(
            store,
            user_id=context.user_id or "",
            subject_type="animal",
            subject_id=context.animal_id or "",
            memory_type=memory_type,
            content=content,
            source=source,
            session_id=session_id,
            operation_id=operation_id,
            ttl_days=context.settings.long_term_memory.ttl_days,
        )
    except Exception:
        return {
            "status": "error",
            "error_code": "MEMORY_WRITE_FAILED",
            "memory_type": memory_type,
        }
    return result.model_dump(mode="json")


def _consultation_memory_content(state: MultiAgentState) -> dict[str, Any]:
    content: dict[str, Any] = {"user_query": state.user_query}
    understanding = _last_disease_understanding(state)
    if understanding is None:
        return content
    for key in (
        "case_summary",
        "species",
        "observed_signs",
        "context_factors",
        "explicit_user_facts",
        "source_spans",
    ):
        value = understanding.get(key)
        if value not in (None, "", [], {}):
            content[key] = value
    return content


def _record_memory_trace(
    state: MultiAgentState,
    node: str,
    status: str,
    record_count: int,
) -> None:
    state.agent_trace.append(
        {
            "node": node,
            "status": status,
            "record_count": record_count,
        }
    )


def _build_disease_context(state: MultiAgentState) -> SessionContextData:
    understanding = _last_disease_understanding(state)
    confirmed: dict[str, object] = {}
    if understanding is not None:
        for key in ("case_summary", "species", "observed_signs", "context_factors", "explicit_user_facts"):
            value = understanding.get(key)
            if value not in (None, "", [], {}):
                confirmed[key] = value
    return SessionContextData(
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
        pending_questions=_disease_follow_up_questions(state),
        answered_questions=list(confirmed),
        last_understanding=understanding,
        last_reasoning_result=_last_disease_reasoning(state),
        evidence_refs=_disease_evidence_refs(state),
        slot_sources={},
        risk_context_status=str((state.disease_assessment or {}).get("status") or "active"),
    )


def _disease_follow_up_questions(state: MultiAgentState) -> list[str]:
    reasoning = _last_disease_reasoning(state)
    raw: list[Any] = []
    if isinstance(reasoning, dict):
        raw = list(reasoning.get("follow_up_questions") or [])
    if not raw and isinstance(state.disease_assessment, dict):
        raw = list(state.disease_assessment.get("follow_up_questions") or [])
    if not raw:
        raw = list(state.session_context.get("pending_questions") or [])
    return list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))[:3]


def _last_disease_reasoning(state: MultiAgentState) -> dict[str, Any] | None:
    for key in ("disease_reasoning", "disease_reasoning_shadow"):
        record = state.tool_results.get(key)
        if isinstance(record, dict) and isinstance(record.get("reasoning"), dict):
            return record["reasoning"]
    return None


def _disease_evidence_refs(state: MultiAgentState) -> list[dict[str, Any]]:
    rag_result = state.tool_results.get(RAG_TOOL_NAME)
    if not isinstance(rag_result, dict):
        return []
    refs: list[dict[str, Any]] = []
    for citation in rag_result.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        source_uri = citation.get("source_uri")
        chunk_id = citation.get("chunk_id")
        if source_uri and chunk_id:
            refs.append({"source_uri": source_uri, "chunk_id": chunk_id})
    return refs


def _gap_to_question(gap: str, query: str) -> str:
    normalized = gap.strip()
    if normalized.endswith(("?", "？")):
        return normalized
    if re.search(r"[\u3400-\u9fff]", query):
        return f"请补充：{normalized}？"
    return f"Please provide: {normalized}?"


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
