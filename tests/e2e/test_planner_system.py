from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from backend.app.agent.graph import run_disease_graph
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.main import create_app
from backend.app.schemas.rag_server import RagSearchResult


class ScriptedRagClient(FakeRagServerClient):
    def __init__(self, error_codes: list[str | None] | None = None) -> None:
        super().__init__()
        self.error_codes = list(error_codes or [])
        self.query_count = 0

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        if not self.error_codes:
            return await super().query(query, **kwargs)
        index = min(self.query_count - 1, len(self.error_codes) - 1)
        error_code = self.error_codes[index]
        if error_code is None:
            return await super().query(query, **kwargs)
        return RagSearchResult(
            query=query,
            status="error",
            error_code=error_code,
            error_message="scripted planner system failure",
        )


def _ask(rag_client: ScriptedRagClient, *, session_id: str) -> dict[str, Any]:
    app = create_app(settings=Settings(database={"url": "sqlite:///:memory:"}))
    app.state.rag_client = rag_client
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "query": "How should cattle feeding be managed?",
                "session_id": session_id,
            },
        )
    assert response.status_code == 200
    assert response.json()["code"] == 0
    return response.json()["data"]


def test_public_chat_completes_a_verified_multi_step_plan() -> None:
    rag_client = ScriptedRagClient()

    data = _ask(rag_client, session_id="planner_system_success")

    planning = data["agent_runtime_debug"]["planning"]
    assert rag_client.query_count == 1
    assert planning["status"] == "completed"
    assert planning["step_count"] == 2
    assert planning["completed_step_count"] == 2
    assert planning["execution_count"] == 2
    assert planning["replan_count"] == 0
    assert planning["final_decision"] == "goal"
    assert data["sources"]


def test_public_chat_retries_one_transient_failure_without_replanning() -> None:
    rag_client = ScriptedRagClient(["RAG_TRANSIENT", None])

    data = _ask(rag_client, session_id="planner_system_retry")

    planning = data["agent_runtime_debug"]["planning"]
    assert rag_client.query_count == 2
    assert planning["status"] == "completed"
    assert planning["execution_count"] == 3
    assert planning["failed_step_count"] == 1
    assert planning["replan_count"] == 0
    assert "rag_retry_history" in data["tools_used"]
    assert data["sources"]


def test_public_chat_bounds_persistent_failures_and_replans_to_safe_fallback() -> None:
    rag_client = ScriptedRagClient(["RAG_TRANSIENT"])

    data = _ask(rag_client, session_id="planner_system_replan")

    planning = data["agent_runtime_debug"]["planning"]
    assert rag_client.query_count == 2
    assert planning["status"] == "completed"
    assert planning["revision"] == 2
    assert planning["source"] == "replan"
    assert planning["step_count"] == 1
    assert planning["execution_count"] == 3
    assert planning["replan_count"] == 1
    assert data["agent_runtime_debug"]["agent_path"].count("replan") == 1
    assert "plan_safe_fallback" in data["tools_used"]
    assert data["sources"] == []


def test_public_chat_does_not_retry_or_replan_permanent_environment_failure() -> None:
    rag_client = ScriptedRagClient(["RAG_SERVER_PATH_MISSING"])

    data = _ask(rag_client, session_id="planner_system_permanent")

    planning = data["agent_runtime_debug"]["planning"]
    assert rag_client.query_count == 1
    assert planning["status"] == "terminated"
    assert planning["execution_count"] == 1
    assert planning["replan_count"] == 0
    assert planning["final_decision"] == "terminal"
    assert planning["termination_code"] == "RAG_SERVER_PATH_MISSING"
    assert data["sources"] == []


def test_safety_block_is_final_and_never_routes_back_to_replan() -> None:
    state = asyncio.run(
        run_disease_graph(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草",
            rag_client=FakeRagServerClient(),
            session_id="planner_system_safety",
            unsafe_draft_for_test="确诊为肠炎，使用药物 5 mg/kg。",
        )
    )

    assert state.replan_count == 0
    assert all(item.get("node") != "replan" for item in state.agent_trace)
    assert state.safety_result is not None
    assert state.safety_result["passed"] is False
    assert state.final_answer is not None
    assert "5 mg/kg" not in state.final_answer
    assert "不能提供具体药物剂量" in state.final_answer
