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
