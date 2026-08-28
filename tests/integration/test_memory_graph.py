from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from backend.app.agent.checkpointing import checkpoint_config
from backend.app.agent.graph import run_chat_graph, run_disease_graph
from backend.app.agent.langgraph_workflow import AgentGraphRuntime, build_chat_graph
from backend.app.agent.memory_store import RepositoryMemoryStore
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import MemoryRepository
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_chat_graph_accepts_checkpointer_and_store() -> None:
    checkpointer = InMemorySaver()
    store = InMemoryStore()
    graph = build_chat_graph(checkpointer=checkpointer, store=store)
    state = MultiAgentState(
        session_id="session_memory_graph",
        user_query="Tell me a joke.",
    )

    async def invoke():  # noqa: ANN202
        return await graph.ainvoke(
            state,
            config=checkpoint_config("user_memory_graph", state.session_id),
            context=AgentGraphRuntime(rag_client=FakeRagServerClient()),
        )

    result = MultiAgentState.model_validate(asyncio.run(invoke()))

    assert result.session_id == state.session_id
    assert checkpointer.get(checkpoint_config("user_memory_graph", state.session_id)) is not None


def test_memory_graph_reads_same_animal_across_sessions_and_isolates_users() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    store = RepositoryMemoryStore(MemoryRepository(conn))
    checkpointer = InMemorySaver()
    settings = Settings(long_term_memory={"read_enabled": True, "write_enabled": True})

    async def invoke():  # noqa: ANN202
        first = await run_disease_graph(
            "犊牛腹泻两天，精神差",
            rag_client=FakeRagServerClient(),
            session_id="session_a",
            request_id="request_a",
            user_id="user_a",
            animal_id="yak_032",
            animal_profile={"animal_id": "yak_032", "species": "cattle"},
            memory_scope_authoritative=True,
            checkpointer=checkpointer,
            store=store,
            settings=settings,
        )
        second = await run_disease_graph(
            "今天仍然没有好转",
            rag_client=FakeRagServerClient(),
            session_id="session_b",
            request_id="request_b",
            user_id="user_a",
            animal_id="yak_032",
            animal_profile={"animal_id": "yak_032", "species": "cattle"},
            memory_scope_authoritative=True,
            checkpointer=checkpointer,
            store=store,
            settings=settings,
        )
        isolated = await run_disease_graph(
            "今天仍然没有好转",
            rag_client=FakeRagServerClient(),
            session_id="session_c",
            request_id="request_c",
            user_id="user_b",
            animal_id="yak_032",
            animal_profile={"animal_id": "yak_032", "species": "cattle"},
            memory_scope_authoritative=True,
            checkpointer=checkpointer,
            store=store,
            settings=settings,
        )
        return first, second, isolated

    first, second, isolated = asyncio.run(invoke())

    assert first.tool_results["search_memory"]["count"] == 0
    assert len(first.tool_results["write_memory"]) == 2
    assert second.tool_results["search_memory"]["count"] == 2
    assert len(second.session_context["long_term_memory"]) == 2
    assert isolated.tool_results["search_memory"]["count"] == 0
    assert all(context.chunk_id for context in second.retrieved_contexts)


def test_checkpointed_chat_turn_resets_transient_agent_state() -> None:
    checkpointer = InMemorySaver()

    async def invoke():  # noqa: ANN202
        first = await run_chat_graph(
            "How should cattle feeding be managed?",
            rag_client=FakeRagServerClient(),
            session_id="session_reset",
            user_id="user_reset",
            checkpointer=checkpointer,
        )
        second = await run_chat_graph(
            "Tell me a joke.",
            rag_client=FakeRagServerClient(),
            session_id="session_reset",
            user_id="user_reset",
            checkpointer=checkpointer,
        )
        return first, second

    first, second = asyncio.run(invoke())

    assert "livestock_rag_search" in first.tool_results
    assert second.intent == "out_of_scope"
    assert "livestock_rag_search" not in second.tool_results
    assert second.retrieved_contexts == []
    assert second.errors == []
