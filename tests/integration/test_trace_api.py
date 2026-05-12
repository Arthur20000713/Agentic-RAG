from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import AgentTraceRepository, RagTraceRepository
from backend.app.main import create_app
from backend.app.services.trace_service import TraceService


def _assert_response_contract(payload: dict) -> None:
    assert set(payload) == {"code", "message", "data", "request_id"}
    assert isinstance(payload["request_id"], str)


def test_agent_trace_repository_persists_node_path_latency_and_status() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    agent_traces = AgentTraceRepository(conn)
    trace_service = TraceService(RagTraceRepository(conn), agent_traces)

    trace_id = trace_service.record_agent_trace(
        session_id="s1",
        request_id="req_agent",
        trace=[
            {"node": "supervisor", "status": "success", "latency_ms": 3},
            {"node": "rag_agent", "status": "success", "latency_ms": 12},
        ],
        status="success",
        latency_ms=15,
    )

    stored = agent_traces.get(trace_id)
    rows = agent_traces.list_by_request_id("req_agent")

    assert stored is not None
    assert stored["session_id"] == "s1"
    assert stored["request_id"] == "req_agent"
    assert [item["node"] for item in stored["trace"]] == ["supervisor", "rag_agent"]
    assert stored["trace"][1]["latency_ms"] == 12
    assert stored["status"] == "success"
    assert stored["latency_ms"] == 15
    assert rows[0]["id"] == trace_id


def test_trace_api_returns_agent_trace_bundle() -> None:
    client = TestClient(create_app(settings=Settings(database={"url": "sqlite:///:memory:"})))
    client.app.state.trace_service.record_agent_trace(
        session_id="s1",
        request_id="req_agent",
        trace=[{"node": "supervisor", "status": "success", "latency_ms": 4}],
        status="success",
        latency_ms=4,
    )

    response = client.get("/api/traces/req_agent")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["request_id"] == "req_agent"
    assert payload["data"]["agent_trace"][0]["trace"][0]["node"] == "supervisor"
    assert payload["data"]["agent_trace"][0]["status"] == "success"
    assert payload["data"]["agent_trace"][0]["latency_ms"] == 4
    assert payload["data"]["tool_trace"] == []
    assert payload["data"]["rag_trace"] == []
    assert payload["data"]["safety_result"] is None
    assert payload["data"]["verifier_result"] is None
