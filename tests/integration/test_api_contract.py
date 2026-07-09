from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.core.config import Settings, load_settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.main import create_app
from backend.app.agent.state import MultiAgentState
from backend.app.services.chat_service import build_debug_payload


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


def test_chat_debug_payload_summarizes_disease_llm_without_raw_payload() -> None:
    settings = Settings(
        v3={"enabled": True},
        disease_llm={"enabled": True, "shadow_mode": False},
    )
    state = MultiAgentState(session_id="s_debug_disease", user_query="disease case", intent="disease_consultation")
    state.tool_results["disease_understanding"] = {
        "fallback_used": False,
        "fallback_reason": None,
        "understanding": {"case_summary": "cattle disease case", "source_spans": ["raw user text"]},
    }
    state.tool_results["disease_evidence_gate"] = {
        "allowed": True,
        "error_code": None,
        "evidence_refs": [{"source_uri": "rag://x", "chunk_id": "c1"}],
    }
    state.tool_results["disease_reasoning"] = {
        "status": "success",
        "fallback_used": False,
        "fallback_reason": None,
        "reasoning": {"safe_actions": [{"text": "raw reasoning", "evidence_refs": []}]},
    }
    state.tool_results["disease_reasoning_takeover"] = {"applied": True}

    payload = build_debug_payload(settings, state=state)

    disease_debug = payload["disease_llm"]
    assert disease_debug["enabled"] is True
    assert disease_debug["shadow_mode"] is False
    assert disease_debug["understanding"]["status"] == "success"
    assert disease_debug["evidence_gate"]["allowed"] is True
    assert disease_debug["evidence_gate"]["evidence_ref_count"] == 1
    assert disease_debug["reasoning"]["status"] == "success"
    assert disease_debug["takeover"]["applied"] is True
    assert "understanding" not in disease_debug["understanding"]
    assert "reasoning" not in disease_debug["reasoning"]
    assert "raw user text" not in str(disease_debug)


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


def test_chat_api_answers_assistant_intro_without_rag_or_domain_refusal() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": True},
    )
    client = TestClient(create_app(settings=settings))

    response = client.post("/api/chat", json={"query": "你好，你是谁？", "session_id": "s_intro"})

    payload = response.json()
    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["intent"] == "assistant_intro"
    assert "畜牧" in payload["data"]["answer"]
    assert "超出" not in payload["data"]["answer"]
    assert "livestock_rag_search" not in payload["data"]["tools_used"]


def test_chat_api_v3_intro_uses_model_intent_router_instead_of_precomputed_template() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": True},
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["intent_routing"],
        },
        local_model={"enabled": True},
    )
    client = TestClient(create_app(settings=settings))

    response = client.post("/api/chat", json={"query": "hello", "session_id": "s_intro_model_route"})

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["intent"] == "assistant_intro"
    assert "intent_router_model" in payload["data"]["tools_used"]
    assert "livestock_rag_search" not in payload["data"]["tools_used"]
    assert payload["data"]["v3_debug"]["agent_path"] == [
        "supervisor",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]


def test_chat_api_disease_follow_up_uses_session_context_and_plain_answers() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": True},
    )
    app = create_app(settings=settings)
    app.state.rag_client = FakeRagServerClient()
    client = TestClient(app)

    first = client.post("/api/chat", json={"query": "羊不吃饭", "session_id": "s_sheep_follow"}).json()
    second = client.post(
        "/api/chat",
        json={"query": "1天了，正常体温，就一只这样", "session_id": "s_sheep_follow"},
    ).json()

    assert first["code"] == 0
    assert first["data"]["intent"] == "disease_consultation"
    assert "请先补充以下信息" not in first["data"]["answer"]
    assert "livestock_rag_search" in first["data"]["tools_used"]
    assert second["code"] == 0
    assert second["data"]["intent"] == "disease_consultation"
    assert "目前体温是多少" not in second["data"]["answer"]
    assert "是否有群体发病" not in second["data"]["answer"]
    assert "livestock_rag_search" in second["data"]["tools_used"]


def test_chat_api_model_router_keeps_plain_follow_up_in_disease_context() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": True},
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["intent_routing"],
        },
        local_model={"enabled": True},
    )
    app = create_app(settings=settings)
    app.state.rag_client = FakeRagServerClient()
    client = TestClient(app)

    first = client.post(
        "/api/chat",
        json={"query": "sick calf [species=cattle] [symptom=diarrhea]", "session_id": "s_model_follow"},
    ).json()
    second = client.post(
        "/api/chat",
        json={"query": "[duration_days=1] [group_outbreak=false]", "session_id": "s_model_follow"},
    ).json()

    assert first["code"] == 0
    assert first["data"]["intent"] == "disease_consultation"
    assert second["code"] == 0
    assert second["data"]["intent"] == "disease_consultation"
    assert "livestock_rag_search" in second["data"]["tools_used"]
    assert "slot_extractor" not in second["data"]["tools_used"]
    assert "disease_slot_router" not in second["data"]["tools_used"]


def test_chat_api_product_config_uses_v3_local_structured_takeover_path() -> None:
    app = create_app(settings=load_settings("config/settings.yaml"))
    app.state.rag_client = FakeRagServerClient()
    client = TestClient(app)

    response = client.post("/api/chat", json={"query": "How should cattle feeding be managed?", "session_id": "s_v6"})

    payload = response.json()
    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["v3_debug"]["v3_enabled"] is True
    assert payload["data"]["v3_debug"]["flags"]["model_router_enabled"] is True
    assert payload["data"]["v3_debug"]["flags"]["model_router_shadow_mode"] is False
    assert payload["data"]["v3_debug"]["flags"]["model_router_low_risk_takeover_enabled"] is True
    assert payload["data"]["v3_debug"]["flags"]["disease_llm_enabled"] is True
    assert payload["data"]["v3_debug"]["flags"]["disease_llm_shadow_mode"] is False


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


def test_health_api_reports_liveness_without_external_dependencies() -> None:
    client = _client()

    response = client.get("/api/health")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["app"] == "Livestock Agentic RAG"
    assert payload["data"]["environment"] == "local"


def test_ready_api_reports_runtime_diagnostics_without_fallback() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        rag_server={
            "query_mode": "real",
            "repo_path": None,
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "strict_real_mode": True,
        },
    )
    client = TestClient(create_app(settings=settings))

    response = client.get("/api/ready")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["status"] == "failed"
    assert payload["data"]["checks"]["default_real_rag"]["status"] == "passed"
    assert payload["data"]["checks"]["rag_server_path"]["error_code"] == "RAG_SERVER_PATH_INVALID"


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
