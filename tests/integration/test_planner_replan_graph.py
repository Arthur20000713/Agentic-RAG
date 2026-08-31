from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.langgraph_workflow import AgentGraphRuntime, build_chat_graph
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.schemas.rag_server import RagSearchResult


class CountingRagClient(FakeRagServerClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        return await super().query(query, **kwargs)


class AlwaysErrorRagClient(FakeRagServerClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        return RagSearchResult(
            query=query,
            status="error",
            error_code="RAG_TRANSIENT",
            error_message="controlled transient failure",
        )


class TransientRagClient(CountingRagClient):
    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        if self.query_count == 1:
            return RagSearchResult(
                query=query,
                status="error",
                error_code="RAG_TRANSIENT",
                error_message="controlled transient failure",
            )
        return await FakeRagServerClient.query(self, query, **kwargs)


def _run(client: FakeRagServerClient) -> MultiAgentState:
    graph = build_chat_graph()
    state = MultiAgentState(
        session_id="session_planner_graph",
        request_id="request_planner_graph",
        user_query="How should cattle feeding be managed?",
    )

    async def invoke() -> Any:
        return await asyncio.wait_for(
            graph.ainvoke(
                state,
                context=AgentGraphRuntime(settings=Settings(), rag_client=client),
            ),
            timeout=3,
        )

    raw = asyncio.run(invoke())
    return raw if isinstance(raw, MultiAgentState) else MultiAgentState.model_validate(raw)


def test_graph_executes_structured_plan_and_verifies_overall_goal() -> None:
    client = CountingRagClient()

    state = _run(client)

    assert client.query_count == 1
    assert state.task_plan is not None
    assert [step.action for step in state.task_plan.steps] == [
        "query_knowledge_hub",
        "compose_grounded_answer",
    ]
    assert state.execution_count == 2
    assert state.plan_verification is not None
    assert state.plan_verification.decision == "goal"
    assert state.replan_count == 0
    trace_nodes = [item["node"] for item in state.agent_trace]
    assert "planner" in trace_nodes
    assert trace_nodes.count("executor") == 2
    assert trace_nodes.count("plan_verifier") == 2


def test_graph_replans_after_retry_budget_and_preserves_safe_boundaries() -> None:
    client = AlwaysErrorRagClient()

    state = _run(client)

    assert client.query_count == 2
    assert state.task_plan is not None
    assert state.task_plan.revision == 2
    assert state.task_plan.source == "replan"
    assert [step.action for step in state.task_plan.steps] == ["safe_fallback"]
    assert state.replan_count == 1
    assert state.replan_history[0].failure_code == "RAG_TRANSIENT"
    assert state.execution_failure is None
    assert state.final_answer
    assert state.tool_results["response_agent"]["sources"] == []
    assert [item["node"] for item in state.agent_trace].count("replan") == 1


def test_transient_error_recovers_by_retry_without_counting_as_replan() -> None:
    client = TransientRagClient()

    state = _run(client)

    assert client.query_count == 2
    assert state.task_plan is not None
    assert state.task_plan.revision == 1
    assert state.replan_count == 0
    assert state.replan_history == []
    assert state.evidence_status == "success"
    assert state.final_answer
    assert not [item for item in state.agent_trace if item.get("node") == "replan"]
