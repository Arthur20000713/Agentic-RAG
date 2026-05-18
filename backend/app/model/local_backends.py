from __future__ import annotations

import inspect
import json
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.app.model.local_schema import parse_local_json_response


LocalTransport = Callable[[str, dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True)
class LocalBackendRequest:
    prompt: str
    schema_name: str
    endpoint: str
    model: str
    timeout_seconds: float = 3.0
    context: dict[str, Any] | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalBackendResponse:
    status: str
    schema_name: str
    content: dict[str, Any]
    fallback_required: bool
    provider: str
    latency_ms: int
    raw_text: str | None = None
    error_code: str | None = None
    reason: str | None = None
    request_payload: dict[str, Any] | None = None


class BaseLocalBackend(ABC):
    provider: str

    @abstractmethod
    async def generate(self, request: LocalBackendRequest) -> LocalBackendResponse:
        """Generate structured local-model output or a structured fallback result."""


class OllamaBackend(BaseLocalBackend):
    provider = "ollama"

    def __init__(self, transport: LocalTransport | None = None) -> None:
        self._transport = transport or _post_json

    async def generate(self, request: LocalBackendRequest) -> LocalBackendResponse:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": False,
            "format": "json",
        }
        if request.options:
            payload["options"] = request.options

        url = _ollama_generate_url(request.endpoint)
        try:
            raw = self._transport(url, payload, request.timeout_seconds)
            if inspect.isawaitable(raw):
                raw = await raw
        except TimeoutError as exc:
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_TIMEOUT",
                reason=str(exc) or "local model request timed out",
            )
        except Exception as exc:
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_HTTP_ERROR",
                reason=str(exc) or exc.__class__.__name__,
            )

        if not isinstance(raw, dict):
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_HTTP_ERROR",
                reason="local model response must be a JSON object",
            )
        if raw.get("error"):
            return self._failure(
                request,
                payload,
                started,
                error_code="LOCAL_MODEL_HTTP_ERROR",
                reason=str(raw["error"]),
            )

        raw_text = _extract_ollama_text(raw)
        content = parse_local_json_response(raw_text, request.schema_name)
        return LocalBackendResponse(
            status=str(content.get("status", "success")),
            schema_name=request.schema_name.strip().lower(),
            content=content,
            fallback_required=bool(content.get("fallback_required")),
            provider=self.provider,
            latency_ms=_latency_ms(started),
            raw_text=raw_text,
            error_code=content.get("error_code"),
            reason=content.get("reason"),
            request_payload=payload,
        )

    def _failure(
        self,
        request: LocalBackendRequest,
        payload: dict[str, Any],
        started: float,
        *,
        error_code: str,
        reason: str,
    ) -> LocalBackendResponse:
        content = {
            "status": "error",
            "schema_name": request.schema_name.strip().lower(),
            "fallback_required": True,
            "error_code": error_code,
            "reason": reason,
        }
        return LocalBackendResponse(
            status="error",
            schema_name=request.schema_name.strip().lower(),
            content=content,
            fallback_required=True,
            provider=self.provider,
            latency_ms=_latency_ms(started),
            error_code=error_code,
            reason=reason,
            request_payload=payload,
        )


def _ollama_generate_url(endpoint: str) -> str:
    return endpoint.rstrip("/") + "/api/generate"


def _extract_ollama_text(raw: dict[str, Any]) -> str:
    response = raw.get("response")
    if isinstance(response, str):
        return response
    message = raw.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    return ""


def _latency_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("local model HTTP response must be a JSON object")
    return parsed
