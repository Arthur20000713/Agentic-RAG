from __future__ import annotations

import asyncio
from typing import Any

from backend.app.model.local_backends import LocalBackendRequest, OllamaBackend
from backend.app.model.local_schema import parse_local_json_response


def test_parse_local_json_response_adds_schema_metadata() -> None:
    result = parse_local_json_response('{"normalized_query": "calf feed"}', schema_name="query_normalization")

    assert result == {
        "normalized_query": "calf feed",
        "status": "success",
        "schema_name": "query_normalization",
        "fallback_required": False,
    }


def test_parse_local_json_response_returns_fallback_for_non_json_text() -> None:
    result = parse_local_json_response("not json", schema_name="slot_extraction")

    assert result["status"] == "error"
    assert result["schema_name"] == "slot_extraction"
    assert result["fallback_required"] is True
    assert result["error_code"] == "LOCAL_MODEL_SCHEMA_ERROR"


def test_ollama_backend_builds_json_generation_payload() -> None:
    captured: dict[str, Any] = {}

    def fake_transport(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return {"response": '{"normalized_query": "weaning feed"}'}

    backend = OllamaBackend(transport=fake_transport)
    request = LocalBackendRequest(
        prompt="weaning feed",
        schema_name="query_normalization",
        endpoint="http://127.0.0.1:11434",
        model="qwen2.5:7b-instruct",
        timeout_seconds=8,
    )

    response = asyncio.run(backend.generate(request))

    assert captured == {
        "url": "http://127.0.0.1:11434/api/generate",
        "payload": {
            "model": "qwen2.5:7b-instruct",
            "prompt": "weaning feed",
            "stream": False,
            "format": "json",
        },
        "timeout_seconds": 8,
    }
    assert response.status == "success"
    assert response.fallback_required is False
    assert response.content["normalized_query"] == "weaning feed"


def test_ollama_backend_returns_structured_timeout_failure() -> None:
    def timeout_transport(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        raise TimeoutError("slow local model")

    backend = OllamaBackend(transport=timeout_transport)
    request = LocalBackendRequest(
        prompt="extract slots",
        schema_name="slot_extraction",
        endpoint="http://127.0.0.1:11434",
        model="qwen2.5:7b-instruct",
        timeout_seconds=1,
    )

    response = asyncio.run(backend.generate(request))

    assert response.status == "error"
    assert response.fallback_required is True
    assert response.error_code == "LOCAL_MODEL_TIMEOUT"
    assert response.content["fallback_required"] is True
