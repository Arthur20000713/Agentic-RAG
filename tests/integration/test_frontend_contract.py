from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _client() -> TestClient:
    settings = Settings(database={"url": "sqlite:///:memory:"})
    return TestClient(create_app(settings=settings))


def test_frontend_chat_page_static_contract() -> None:
    response = _client().get("/app")

    assert response.status_code == 200
    assert 'id="chat-form"' in response.text
    assert 'id="chat-query"' in response.text
    assert 'data-view="chat"' in response.text


def test_frontend_chat_js_contract() -> None:
    response = _client().get("/app/app.js")

    assert response.status_code == 200
    assert "function renderChat" in response.text
    assert "async function submitChat" in response.text
    assert 'fetch("/api/chat"' in response.text
    assert "risk_level" in response.text
    assert "follow_up_questions" in response.text


def test_frontend_sources_and_tools_contract() -> None:
    client = _client()

    js = client.get("/app/app.js").text
    chat = client.post("/api/chat", json={"query": "How should cattle feeding be managed?"}).json()

    assert "function renderSources" in js
    assert "function renderToolSummary" in js
    assert "source_uri" in js
    assert "tools_used" in js
    assert chat["data"]["sources"][0]["source_uri"].startswith("rag://")
    assert "livestock_rag_search" in chat["data"]["tools_used"]


def test_frontend_measurement_contract() -> None:
    client = _client()

    html = client.get("/app").text
    js = client.get("/app/app.js").text
    response = client.post(
        "/api/measurement/analyze",
        json={
            "animal_id": "yak_032",
            "current": {"chest_girth_cm": 158.4},
            "confidence": 0.82,
            "use_demo_history": True,
        },
    ).json()

    assert 'id="measurement-form"' in html
    assert 'id="measurement-result"' in html
    assert "function renderMeasurement" in js
    assert "async function submitMeasurement" in js
    assert 'fetch("/api/measurement/analyze"' in js
    assert "abnormal_items" in js
    assert response["data"]["report"]
    assert response["data"]["evidence"]


def test_frontend_debug_panel_contract() -> None:
    client = _client()

    html = client.get("/app").text
    js = client.get("/app/app.js").text
    trace = client.get("/api/traces/req_debug").json()
    rag_status = client.get("/api/rag/status").json()

    assert 'id="debug-json"' in html
    assert "function renderDebugPanel" in js
    assert "function buildDebugSummary" in js
    assert 'fetch("/api/rag/status"' in js
    for field in ("request_id", "rag_mode", "agent_path", "safety", "verifier"):
        assert field in js
    assert trace["data"]["request_id"] == "req_debug"
    assert "agent_trace" in trace["data"]
    assert rag_status["data"]["rag_mode"] == "fake"


def test_frontend_debug_panel_can_show_v3_debug_payload() -> None:
    client = _client()

    js = client.get("/app/app.js").text
    chat = client.post("/api/chat", json={"query": "How should cattle feeding be managed?"}).json()

    assert "v3_debug" in chat["data"]
    assert chat["data"]["v3_debug"]["v3_enabled"] is False
    assert "raw" in js
