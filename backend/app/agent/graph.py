from __future__ import annotations

from typing import Any
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph

from backend.app.agent.langgraph_workflow import (
    AgentGraphRuntime,
    build_chat_graph,
    build_measurement_graph,
    merge_session_slots,
)
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.model.base import BaseModelClient
from backend.app.model.intent_router import route_intent_with_model
from backend.app.schemas.agent import IntentType
from backend.app.schemas.measurement import MeasurementInput
from backend.app.services.memory_service import MemoryService
from backend.app.services.session_context_service import SessionContextService


_CHAT_GRAPH = build_chat_graph()
_MEASUREMENT_GRAPH = build_measurement_graph()


def get_chat_graph() -> CompiledStateGraph:
    """Return the compiled production chat graph for topology and diagnostics."""

    return _CHAT_GRAPH


def get_measurement_graph() -> CompiledStateGraph:
    """Return the compiled production measurement graph."""

    return _MEASUREMENT_GRAPH


async def run_chat_graph(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_context_service: SessionContextService | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    animal_id: str | None = None,
    memory_service: MemoryService | None = None,
    settings: Settings | None = None,
    query_normalizer_client: BaseModelClient | None = None,
    intent_router_client: BaseModelClient | None = None,
    primary_llm_client: Any | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    forced_intent: IntentType | None = None,
    unsafe_draft_for_test: str | None = None,
) -> MultiAgentState:
    """Run one chat turn through the unified LangGraph workflow."""

    app_settings = settings or Settings()
    state = MultiAgentState(
        session_id=session_id or _new_session_id(),
        request_id=request_id,
        user_query=query,
    )
    runtime = AgentGraphRuntime(
        settings=app_settings,
        rag_client=rag_client or FakeRagServerClient(),
        session_context_service=session_context_service,
        memory_service=memory_service,
        query_normalizer_client=query_normalizer_client,
        intent_router_client=intent_router_client,
        intent_router=route_intent_with_model,
        primary_llm_client=primary_llm_client,
        conversation_history=list(conversation_history or []),
        forced_intent=forced_intent,
        animal_id=animal_id,
        unsafe_draft_for_test=unsafe_draft_for_test,
    )
    raw = await _CHAT_GRAPH.ainvoke(state, context=runtime)
    return MultiAgentState.model_validate(raw)


async def run_general_qa_graph(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    settings: Settings | None = None,
    query_normalizer_client: BaseModelClient | None = None,
    primary_llm_client: Any | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> MultiAgentState:
    """Compatibility facade for callers that require the general-QA branch."""

    return await run_chat_graph(
        query,
        rag_client=rag_client,
        session_id=session_id,
        request_id=request_id,
        settings=settings,
        query_normalizer_client=query_normalizer_client,
        primary_llm_client=primary_llm_client,
        conversation_history=conversation_history,
    )


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
    conversation_history: list[dict[str, Any]] | None = None,
) -> MultiAgentState:
    """Compatibility facade for callers that require the disease branch."""

    return await run_chat_graph(
        query,
        rag_client=rag_client,
        session_context_service=session_context_service,
        session_id=session_id,
        request_id=request_id,
        animal_id=animal_id,
        memory_service=memory_service,
        settings=settings,
        query_normalizer_client=query_normalizer_client,
        primary_llm_client=primary_llm_client,
        conversation_history=conversation_history,
        forced_intent="disease_consultation",
        unsafe_draft_for_test=unsafe_draft_for_test,
    )


async def run_measurement_graph(
    measurement: MeasurementInput,
    *,
    session_id: str | None = None,
    memory_service: MemoryService | None = None,
    settings: Settings | None = None,
) -> MultiAgentState:
    """Run structured body-measurement analysis through LangGraph."""

    app_settings = settings or Settings()
    state = MultiAgentState(
        session_id=session_id or _new_session_id(),
        user_query=f"body measurement analysis for {measurement.animal_id}",
    )
    runtime = AgentGraphRuntime(
        settings=app_settings,
        measurement=measurement,
        memory_service=memory_service,
        forced_intent="measurement_analysis",
        intent_router=route_intent_with_model,
    )
    raw = await _MEASUREMENT_GRAPH.ainvoke(state, context=runtime)
    return MultiAgentState.model_validate(raw)


def _new_session_id() -> str:
    return f"s_{uuid4().hex}"


__all__ = [
    "get_chat_graph",
    "get_measurement_graph",
    "merge_session_slots",
    "run_chat_graph",
    "run_disease_graph",
    "run_general_qa_graph",
    "run_measurement_graph",
]
