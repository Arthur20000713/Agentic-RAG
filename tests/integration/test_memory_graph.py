from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from backend.app.agent.checkpointing import checkpoint_config, open_sqlite_checkpointer
from backend.app.agent.graph import run_chat_graph, run_disease_graph
from backend.app.agent.langgraph_workflow import (
    AgentGraphRuntime,
    build_chat_graph,
    resume_chat_graph,
)
from backend.app.agent.memory_store import RepositoryMemoryStore
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import MemoryRepository
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.schemas.rag_server import RagSearchResult


class CountingRagClient(FakeRagServerClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        return await super().query(query, **kwargs)


class CountingTriageClient:
    def __init__(self) -> None:
        self.call_count = 0

    async def generate_json(self, prompt: str, *, schema_name: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        self.call_count += 1
        assert schema_name == "livestock_triage"
        assert context == {"user_query": "How should cattle feeding be managed?"}
        return {
            "status": "success",
            "schema_name": "livestock_triage",
            "fallback_required": False,
            "intent_candidate": "general_qa",
            "confidence": 0.9,
            "slots": [],
            "risk_candidate": "low",
            "risk_signals": [],
        }


def _triage_settings(*, shadow_mode: bool = False) -> Settings:
    return Settings(
        model_router={
            "enabled": True,
            "shadow_mode": shadow_mode,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["livestock_triage"],
        },
        local_model={"enabled": True},
    )


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
    assert first.agentic_retrieval is not None
    assert second.intent == "out_of_scope"
    assert "livestock_rag_search" not in second.tool_results
    assert second.retrieved_contexts == []
    assert second.agentic_retrieval is None
    assert second.errors == []
    assert second.task_plan is None
    assert second.current_step_id is None
    assert second.step_results == []
    assert second.execution_failure is None
    assert second.execution_count == 0
    assert second.plan_verification is None
    assert second.replan_count == 0
    assert second.replan_history == []
    assert second.rag_query is None
    assert second.draft_answer != first.draft_answer
    assert second.final_answer != first.final_answer


def test_checkpoint_resume_does_not_repeat_completed_livestock_triage() -> None:
    checkpointer = InMemorySaver()
    triage_client = CountingTriageClient()
    runtime = AgentGraphRuntime(
        settings=_triage_settings(),
        rag_client=FakeRagServerClient(),
        livestock_triage_client=triage_client,
    )
    config = checkpoint_config("user_triage", "session_triage")
    state = MultiAgentState(
        session_id="session_triage",
        request_id="request_triage",
        user_query="How should cattle feeding be managed?",
    )

    async def invoke() -> MultiAgentState:
        interrupted_graph = build_chat_graph(checkpointer=checkpointer, interrupt_after=["livestock_triage"])
        interrupted = await interrupted_graph.ainvoke(state, context=runtime, config=config)
        assert interrupted["livestock_triage"]["status"] == "accepted"
        assert (await interrupted_graph.aget_state(config)).next == ("router",)
        return await resume_chat_graph(build_chat_graph(checkpointer=checkpointer), runtime=runtime, config=config)

    result = asyncio.run(invoke())

    assert triage_client.call_count == 1
    assert result.livestock_triage is not None
    assert result.livestock_triage.status == "accepted"


def test_new_checkpointed_turn_drops_old_triage_when_router_is_disabled() -> None:
    checkpointer = InMemorySaver()
    triage_client = CountingTriageClient()

    async def invoke() -> tuple[MultiAgentState, MultiAgentState]:
        first = await run_chat_graph(
            "How should cattle feeding be managed?",
            session_id="session_triage_reset",
            user_id="user_triage_reset",
            checkpointer=checkpointer,
            settings=_triage_settings(),
            livestock_triage_client=triage_client,
        )
        second = await run_chat_graph(
            "Tell me a short joke.",
            session_id="session_triage_reset",
            user_id="user_triage_reset",
            checkpointer=checkpointer,
            settings=Settings(),
            livestock_triage_client=triage_client,
        )
        return first, second

    first, second = asyncio.run(invoke())

    assert first.livestock_triage is not None
    assert second.livestock_triage is None
    assert "livestock_triage" not in second.tool_results


def test_sqlite_checkpoint_resume_does_not_repeat_completed_step(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "planner_resume.sqlite3"
    config = checkpoint_config("user_resume", "session_resume")
    client = CountingRagClient()
    runtime = AgentGraphRuntime(settings=Settings(), rag_client=client)
    state = MultiAgentState(
        session_id="session_resume",
        request_id="request_resume",
        user_query="How should cattle feeding be managed?",
    )

    async def invoke() -> MultiAgentState:
        async with open_sqlite_checkpointer(checkpoint_path) as saver:
            graph = build_chat_graph(
                checkpointer=saver,
                interrupt_after=["executor"],
            )
            interrupted = await graph.ainvoke(state, context=runtime, config=config)
            snapshot = await graph.aget_state(config)
            assert snapshot.next == ("plan_verifier",)
            assert interrupted["execution_count"] == 1
            assert client.query_count == 1

        async with open_sqlite_checkpointer(checkpoint_path) as saver:
            graph = build_chat_graph(checkpointer=saver)
            return await resume_chat_graph(graph, runtime=runtime, config=config)

    result = asyncio.run(invoke())

    assert client.query_count == 1
    assert result.agentic_retrieval is not None
    assert result.execution_count == 2
    assert [item.step_id for item in result.step_results] == ["retrieve", "compose"]
    assert result.plan_verification is not None
    assert result.plan_verification.decision == "goal"
    assert result.final_answer
