from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import AgentTraceRepository, MemoryRepository, RagTraceRepository
from backend.app.main import create_app
from backend.app.services.memory_service import MemoryEvent
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
    assert payload["data"]["agent_runtime_debug_summary"]["flags"]["agent_runtime_engine"] == "langgraph"
    assert payload["data"]["agent_runtime_debug_summary"]["route"]["status"] == "not_available"


def test_trace_api_returns_rag_trace_bundle() -> None:
    client = TestClient(create_app(settings=Settings(database={"url": "sqlite:///:memory:"})))
    client.app.state.trace_service.record_rag_call(
        session_id="s1",
        request_id="req_rag",
        rag_mode="real",
        collection="livestock_v4_1",
        query="calf diarrhea",
        top_k=4,
        result_count=2,
        mapped_result_count=2,
        top_score=0.82,
        raw_response_id="raw_1",
        status="success",
        attempt_count=1,
        latency_ms=120,
    )

    response = client.get("/api/traces/req_rag")
    payload = response.json()

    assert response.status_code == 200
    assert payload["data"]["rag_trace"][0]["request_id"] == "req_rag"
    assert payload["data"]["rag_trace"][0]["rag_mode"] == "real"
    assert payload["data"]["rag_trace"][0]["collection"] == "livestock_v4_1"
    assert payload["data"]["rag_trace"][0]["attempt_count"] == 1


def test_chat_request_id_can_query_langgraph_agent_trace() -> None:
    settings = Settings(database={"url": "sqlite:///:memory:"})
    client = TestClient(create_app(settings=settings))

    chat_response = client.post("/api/chat", json={"query": "How should cattle feeding be managed?", "session_id": "s_trace"})
    chat_payload = chat_response.json()
    request_id = chat_payload["request_id"]

    trace_response = client.get(f"/api/traces/{request_id}")
    trace_payload = trace_response.json()
    data = trace_payload["data"]

    assert chat_response.status_code == 200
    assert trace_response.status_code == 200
    assert data["request_id"] == request_id
    assert data["agent_trace"][0]["request_id"] == request_id
    assert data["agent_runtime_debug_summary"]["agent_path"] == [
        "supervisor",
        "rag_agent",
        "grounded_answer_agent",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]
    assert data["safety_result"]["passed"] is True
    assert data["verifier_result"]["passed"] is True


def test_trace_api_returns_agent_runtime_debug_summary_for_route_safety_and_memory() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        model_router={"enabled": True, "shadow_mode": True},
        long_term_memory={"write_enabled": True},
    )
    client = TestClient(create_app(settings=settings))
    client.app.state.trace_service.record_agent_trace(
        session_id="s1",
        request_id="req_agent_runtime_debug",
        trace=[
            {
                "node": "model_router_shadow",
                "status": "success",
                "route_mode": "shadow",
                "selected_model": "primary",
                "shadow_model": "local_small",
                "safety_level": "S1",
                "local_candidate_allowed": True,
                "latency_ms": 1,
            },
            {
                "node": "safety_agent",
                "status": "blocked",
                "passed": False,
                "violations": ["dosage"],
                "hard_blocked": True,
                "violation_count": 1,
                "latency_ms": 2,
            },
        ],
        status="blocked",
        latency_ms=3,
    )
    MemoryRepository(client.app.state.db_conn).append_event(
        MemoryEvent(
            event_id="mem_trace_debug",
            subject_type="animal",
            subject_id="yak_032",
            event_type="upsert",
            source="user_confirmed",
            payload={"fact_type": "measurement", "value": {"current": {"weight_kg": 246.5}}, "metadata": {}},
        )
    )

    response = client.get("/api/traces/req_agent_runtime_debug")
    payload = response.json()
    summary = payload["data"]["agent_runtime_debug_summary"]

    assert response.status_code == 200
    assert summary["flags"]["agent_runtime_engine"] == "langgraph"
    assert summary["route"]["route_mode"] == "shadow"
    assert summary["route"]["shadow_model"] == "local_small"
    assert summary["safety"]["passed"] is False
    assert summary["safety"]["hard_blocked"] is True
    assert summary["memory"]["write_enabled"] is True
    assert summary["memory"]["event_count"] == 1
    assert summary["rag_status"]["rag_mode"] == "fake"
    assert summary["rag_status"]["collection"] == "default"
    assert summary["rag_status"]["quality_gate_status"] == "not_configured"
