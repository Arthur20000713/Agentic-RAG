from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _client() -> TestClient:
    settings = Settings(database={"url": "sqlite:///:memory:"})
    return TestClient(create_app(settings=settings))


def test_frontend_static_page_and_assets_smoke() -> None:
    client = _client()

    page = client.get("/app")
    script = client.get("/app/app.js")
    styles = client.get("/app/styles.css")

    assert page.status_code == 200
    assert script.status_code == 200
    assert styles.status_code == 200
    assert "畜牧业 Agentic RAG 智能助手" in page.text
    assert "submitChat" in script.text
    assert "submitMeasurement" in script.text


def test_frontend_chat_demo_smoke() -> None:
    response = _client().post(
        "/api/chat",
        json={"query": "How should cattle feeding be managed?", "session_id": "s_frontend_chat"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["answer"]
    assert payload["data"]["intent"] == "general_qa"
    assert payload["data"]["sources"]
    assert "livestock_rag_search" in payload["data"]["tools_used"]


def test_frontend_measurement_demo_smoke() -> None:
    response = _client().post(
        "/api/measurement/analyze",
        json={
            "animal_id": "yak_demo",
            "current": {"chest_girth_cm": 158.4},
            "confidence": 0.82,
            "use_demo_history": True,
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["animal_id"] == "yak_demo"
    assert payload["data"]["report"]
    assert payload["data"]["evidence"]
