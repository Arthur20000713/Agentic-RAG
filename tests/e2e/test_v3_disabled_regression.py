from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings=settings))


def _v2_settings() -> Settings:
    return Settings(database={"url": "sqlite:///:memory:"})


def _v3_disabled_settings() -> Settings:
    return Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": False},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
        lora={"dataset_enabled": True, "inference_enabled": True},
        long_term_memory={"write_enabled": True, "read_enabled": True},
        enhanced_safety={"precheck_enabled": True, "final_guard_required": True},
    )


def _post_ok(client: TestClient, path: str, payload: dict) -> dict:
    response = client.post(path, json=payload)
    body = response.json()

    assert response.status_code == 200
    assert body["code"] == 0
    return body["data"]


def test_v3_disabled_general_qa_matches_v2_path() -> None:
    payload = {
        "query": "How should calf feeding management be handled after weaning?",
        "session_id": "s_v3_disabled_general",
    }

    v2_data = _post_ok(_client(_v2_settings()), "/api/chat", payload)
    disabled_data = _post_ok(_client(_v3_disabled_settings()), "/api/chat", payload)

    assert disabled_data == v2_data
    assert disabled_data["intent"] == "general_qa"
    assert disabled_data["tools_used"] == ["livestock_rag_search"]
    assert disabled_data["v3_debug"]["v3_enabled"] is False
    assert disabled_data["v3_debug"]["flags"]["model_router_enabled"] is False
    assert disabled_data["v3_debug"]["flags"]["memory_write_enabled"] is False


def test_v3_disabled_disease_follow_up_matches_v2_path() -> None:
    payload = {
        "query": "The calf has diarrhea. What should I do?",
        "session_id": "s_v3_disabled_disease",
    }

    v2_data = _post_ok(_client(_v2_settings()), "/api/chat", payload)
    disabled_data = _post_ok(_client(_v3_disabled_settings()), "/api/chat", payload)

    assert disabled_data == v2_data
    assert disabled_data["intent"] == "disease_consultation"
    assert disabled_data["need_follow_up"] is True
    assert disabled_data["tools_used"] == ["slot_extractor"]
    assert "livestock_rag_search" not in disabled_data["tools_used"]
    assert disabled_data["v3_debug"]["flags"]["local_model_enabled"] is False


def test_v3_disabled_measurement_matches_v2_path() -> None:
    payload = {
        "animal_id": "yak_032",
        "current": {"chest_girth_cm": 158.4},
        "confidence": 0.82,
        "use_demo_history": True,
    }

    v2_data = _post_ok(_client(_v2_settings()), "/api/measurement/analyze", payload)
    disabled_data = _post_ok(_client(_v3_disabled_settings()), "/api/measurement/analyze", payload)

    assert disabled_data == v2_data
    assert disabled_data["animal_id"] == "yak_032"
    assert disabled_data["used_demo_history"] is True
    assert disabled_data["evidence"]
