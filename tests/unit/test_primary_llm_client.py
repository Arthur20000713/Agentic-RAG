from __future__ import annotations

import asyncio
from typing import Any

from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest


class RecordingTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any], dict[str, str], float]] = []

    def __call__(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        self.calls.append((url, payload, headers, timeout))
        return self.response


def test_primary_llm_client_calls_openai_compatible_json_api(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    settings = Settings(
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "timeout_seconds": 12,
        }
    )
    transport = RecordingTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"success","species":"sheep","confidence":0.82}'
                    }
                }
            ]
        }
    )
    client = PrimaryLLMClient(settings=settings, transport=transport)

    result = asyncio.run(
        client.generate_json(
            PrimaryLLMRequest(
                prompt="Extract disease case",
                schema_name="disease_case_understanding",
                context={"session_id": "s1"},
            )
        )
    )

    assert result["status"] == "success"
    assert result["species"] == "sheep"
    assert result["provider"] == "deepseek"
    assert result["model"] == "deepseek-v4-flash"
    assert transport.calls[0][0] == "https://api.deepseek.com/chat/completions"
    assert transport.calls[0][1]["response_format"] == {"type": "json_object"}
    assert transport.calls[0][2]["Authorization"] == "Bearer secret-value"
    assert "secret-value" not in str(result)


def test_primary_llm_client_reports_missing_api_key_without_leaking_value(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = Settings(
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
        }
    )
    client = PrimaryLLMClient(settings=settings, transport=RecordingTransport({}))

    result = asyncio.run(
        client.generate_json(
            PrimaryLLMRequest(prompt="Extract disease case", schema_name="disease_case_understanding")
        )
    )

    assert result["status"] == "error"
    assert result["fallback_required"] is True
    assert result["error_code"] == "PRIMARY_LLM_API_KEY_MISSING"
    assert result["api_key_env"] == "DEEPSEEK_API_KEY"
    assert "secret" not in str(result).lower()
