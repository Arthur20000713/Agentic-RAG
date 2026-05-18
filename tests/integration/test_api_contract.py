from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _client() -> TestClient:
    settings = Settings(database={"url": "sqlite:///:memory:"})
    return TestClient(create_app(settings=settings))


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _assert_response_contract(payload: dict) -> None:
    assert set(payload) == {"code", "message", "data", "request_id"}
    assert isinstance(payload["request_id"], str)


def test_chat_api_contract_general_qa() -> None:
    client = _client()

    response = client.post("/api/chat", json={"query": "犊牛腹泻的常见原因是什么？", "session_id": "s1"})

    payload = response.json()
    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["intent"] == "disease_consultation"
    assert "answer" in payload["data"]
    assert "tools_used" in payload["data"]
    assert payload["data"]["v3_debug"]["v3_enabled"] is False
    assert payload["data"]["v3_debug"]["flags"]["final_guard_required"] is True


def test_chat_api_reports_v3_debug_flags_without_changing_v2_fields() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": True},
        long_term_memory={"write_enabled": True, "read_enabled": False},
    )
    client = TestClient(create_app(settings=settings))

    response = client.post("/api/chat", json={"query": "How should cattle feeding be managed?", "session_id": "s_v3"})

    payload = response.json()
    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert "answer" in payload["data"]
    assert "tools_used" in payload["data"]
    assert payload["data"]["v3_debug"]["v3_enabled"] is True
    assert payload["data"]["v3_debug"]["flags"]["model_router_enabled"] is True
    assert payload["data"]["v3_debug"]["flags"]["model_router_shadow_mode"] is True
    assert payload["data"]["v3_debug"]["flags"]["memory_write_enabled"] is True
    assert payload["data"]["v3_debug"]["rag_status"]["quality_gate_status"] == "not_configured"


def test_chat_api_debug_includes_v4_2_rag_status_fields() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        rag_server={"query_mode": "real", "repo_path": None, "collection": "livestock_v4_2"},
    )
    client = TestClient(create_app(settings=settings))

    response = client.post("/api/chat", json={"query": "How should cattle feeding be managed?", "session_id": "s_v4_2"})

    payload = response.json()
    rag_status = payload["data"]["v3_debug"]["rag_status"]
    assert response.status_code == 200
    assert rag_status["rag_mode"] == "real"
    assert rag_status["collection"] == "livestock_v4_2"
    assert rag_status["batch_id"] == "batch_002"
    assert rag_status["quality_gate_status"] == "not_configured"


def test_chat_api_uses_v3_graph_when_feature_flag_enabled() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": True},
    )
    client = TestClient(create_app(settings=settings))

    response = client.post("/api/chat", json={"query": "How should cattle feeding be managed?", "session_id": "s_v3_graph"})

    payload = response.json()
    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["intent"] == "general_qa"
    assert payload["data"]["v3_debug"]["v3_enabled"] is True
    assert payload["data"]["v3_debug"]["agent_path"] == [
        "supervisor",
        "rag_agent",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]
    assert payload["data"]["v3_debug"]["verifier"]["passed"] is True
    assert payload["data"]["v3_debug"]["safety"]["passed"] is True


def test_measurement_api_contract() -> None:
    client = _client()

    response = client.post(
        "/api/measurement/analyze",
        json={
            "animal_id": "yak_032",
            "current": {"chest_girth_cm": 158.4},
            "confidence": 0.82,
            "use_demo_history": True,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["animal_id"] == "yak_032"
    assert "report" in payload["data"]


def test_upload_document_creates_ingestion_task() -> None:
    client = _client()

    response = client.post(
        "/api/documents/upload",
        files={"file": ("guide.txt", b"hello", "text/plain")},
        data={"collection": "default"},
    )

    payload = response.json()
    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["task_id"].startswith("task_")
    assert payload["data"]["status"] == "pending"


def test_get_task_contract() -> None:
    client = _client()
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("guide.txt", b"hello", "text/plain")},
        data={"collection": "default"},
    ).json()

    response = client.get(f"/api/tasks/{upload['data']['task_id']}")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["task_id"] == upload["data"]["task_id"]


def test_index_task_reports_rag_server_missing_path_without_fabrication() -> None:
    client = _client()
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("guide.txt", b"hello", "text/plain")},
        data={"collection": "default"},
    ).json()

    response = client.post(f"/api/tasks/{upload['data']['task_id']}/index")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 50004
    assert payload["data"]["status"] == "failed"
    assert payload["data"]["error_code"] == "RAG_SERVER_PATH_MISSING"


def test_rag_status_api_defaults_to_fake_without_real_path() -> None:
    client = _client()

    response = client.get("/api/rag/status")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["rag_mode"] == "fake"
    assert payload["data"]["rag_mode_effective"] == "fake"
    assert payload["data"]["rag_server_path_configured"] is False
    assert payload["data"]["mcp_available"] is False
    assert payload["data"]["default_collection"] == "default"
    assert payload["data"]["last_rag_error"] is None


def test_rag_status_api_reports_missing_real_path_without_failure() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        rag_server={"query_mode": "real", "repo_path": None, "collection": "livestock_knowledge"},
    )
    client = TestClient(create_app(settings=settings))

    response = client.get("/api/rag/status")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["rag_mode"] == "real"
    assert payload["data"]["rag_mode_effective"] == "real"
    assert payload["data"]["rag_server_path_configured"] is False
    assert payload["data"]["mcp_available"] is False
    assert payload["data"]["default_collection"] == "livestock_knowledge"
    assert payload["data"]["last_rag_error"] == "RAG_SERVER_PATH_MISSING"


def test_rag_status_api_reports_existing_real_path() -> None:
    rag_server_path = _tmp_dir()
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        rag_server={"query_mode": "real", "repo_path": str(rag_server_path), "collection": "livestock_knowledge"},
    )
    client = TestClient(create_app(settings=settings))

    response = client.get("/api/rag/status")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["rag_server_path_configured"] is True
    assert payload["data"]["rag_server_path_exists"] is True
    assert payload["data"]["mcp_available"] is True
    assert payload["data"]["last_rag_error"] is None
