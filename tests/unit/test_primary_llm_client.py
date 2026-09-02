from __future__ import annotations

import asyncio
from typing import Any

import pytest

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
            ],
            "usage": {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50},
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
    assert "usage" not in result
    records = client.drain_model_call_records()
    assert len(records) == 1
    assert records[0].usage.model_dump() == {
        "source": "provider",
        "input_tokens": 40,
        "output_tokens": 10,
        "total_tokens": 50,
    }
    assert records[0].cost.total_cost_usd is None
    assert "Extract disease case" not in str(records[0].model_dump(mode="json"))


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
    record = client.drain_model_call_records()[0]
    assert record.status == "fallback"
    assert record.fallback_reason == "PRIMARY_LLM_API_KEY_MISSING"
    assert record.usage.source == "unavailable"


def test_primary_llm_client_reads_same_key_from_rag_server_env_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    rag_server = tmp_path / "RAG-SERVER"
    rag_server.mkdir()
    (rag_server / ".env").write_text("DEEPSEEK_API_KEY=secret-from-rag-server\n", encoding="utf-8")
    settings = Settings(
        rag_server={"repo_path": str(rag_server)},
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
        },
    )
    transport = RecordingTransport(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"success","species":"cattle","confidence":0.86}'
                    }
                }
            ]
        }
    )

    result = asyncio.run(
        PrimaryLLMClient(settings=settings, transport=transport).generate_json(
            PrimaryLLMRequest(prompt="Extract disease case", schema_name="disease_case_understanding")
        )
    )

    assert result["status"] == "success"
    assert transport.calls[0][2]["Authorization"] == "Bearer secret-from-rag-server"
    assert "secret-from-rag-server" not in str(result)


def test_primary_llm_client_marks_missing_provider_usage_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    settings = Settings(
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
        }
    )
    client = PrimaryLLMClient(
        settings=settings,
        transport=RecordingTransport(
            {"choices": [{"message": {"content": '{"status":"success"}'}}]}
        ),
    )

    asyncio.run(client.generate_json(PrimaryLLMRequest(prompt="secret prompt", schema_name="reasoning")))
    record = client.drain_model_call_records()[0]

    assert record.usage.source == "unavailable"
    assert record.usage.total_tokens is None
    assert record.cost.total_cost_usd is None
    assert "secret prompt" not in str(record.model_dump(mode="json"))


def test_primary_llm_client_records_fallback_usage_without_raw_response(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    settings = Settings(
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
        },
        model_pricing={
            "primary_input_usd_per_million_tokens": 1.0,
            "primary_output_usd_per_million_tokens": 2.0,
        },
    )
    raw_response = {
        "choices": [{"message": {"content": "not-json-private-provider-output"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
    }
    client = PrimaryLLMClient(settings=settings, transport=RecordingTransport(raw_response))

    result = asyncio.run(
        client.generate_json(PrimaryLLMRequest(prompt="private prompt", schema_name="reasoning"))
    )
    record = client.drain_model_call_records()[0]

    assert result["fallback_required"] is True
    assert record.status == "error"
    assert record.usage.total_tokens == 6
    assert record.cost.total_cost_usd == pytest.approx(0.000007)
    assert "not-json-private-provider-output" not in str(record.model_dump(mode="json"))


def test_primary_llm_client_does_not_persist_sensitive_transport_exception(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    settings = Settings(
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
        }
    )

    def failing_transport(url, payload, headers, timeout):  # noqa: ANN001, ANN202
        raise RuntimeError("private prompt=abc Authorization=Bearer secret-value")

    client = PrimaryLLMClient(settings=settings, transport=failing_transport)

    result = asyncio.run(
        client.generate_json(PrimaryLLMRequest(prompt="private prompt", schema_name="reasoning"))
    )
    record = client.drain_model_call_records()[0]
    serialized = str(record.model_dump(mode="json"))

    assert result["reason"] == "RuntimeError"
    assert record.fallback_reason == "PRIMARY_LLM_TRANSPORT_ERROR"
    assert "private prompt" not in serialized
    assert "Authorization" not in serialized
    assert "secret-value" not in serialized


def test_primary_llm_client_does_not_persist_model_fallback_reason(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    settings = Settings(
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
        }
    )
    client = PrimaryLLMClient(
        settings=settings,
        transport=RecordingTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"status":"success","fallback_required":true,'
                                '"error_code":"private prompt secret-value",'
                                '"reason":"private prompt Authorization=Bearer secret-value"}'
                            )
                        }
                    }
                ]
            }
        ),
    )

    asyncio.run(client.generate_json(PrimaryLLMRequest(prompt="private prompt", schema_name="reasoning")))
    record = client.drain_model_call_records()[0]

    assert record.status == "fallback"
    assert record.fallback_reason == "PRIMARY_LLM_FALLBACK"
    serialized = str(record.model_dump(mode="json"))
    assert "private prompt" not in serialized
    assert "Authorization" not in serialized
    assert "secret-value" not in serialized
