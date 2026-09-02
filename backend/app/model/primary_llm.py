from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings
from backend.app.model.local_schema import parse_local_json_response
from backend.app.model.usage import (
    ModelCallRecorder,
    chat_completions_usage,
    unavailable_usage,
)
from backend.app.schemas.model_routing import ModelCallRecord

PrimaryLLMTransport = Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]]


@dataclass(frozen=True)
class PrimaryLLMRequest:
    prompt: str
    schema_name: str
    context: dict[str, Any] | None = None
    system_prompt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PrimaryLLMClient:
    def __init__(self, settings: Settings | None = None, transport: PrimaryLLMTransport | None = None) -> None:
        self.settings = settings or Settings()
        self.transport = transport or _post_json
        self._telemetry = ModelCallRecorder(self.settings, "primary")

    def telemetry_scope(self, operation_prefix: str):
        return self._telemetry.scope(operation_prefix)

    def drain_model_call_records(self) -> list[ModelCallRecord]:
        return self._telemetry.drain()

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        request_started_at = time.perf_counter()
        llm = self.settings.primary_llm
        schema_name = request.schema_name.strip().lower()
        if not llm.enabled:
            result = _fallback(schema_name, "PRIMARY_LLM_DISABLED", "primary LLM is disabled")
            self._record_preflight_fallback(schema_name, "PRIMARY_LLM_DISABLED", request_started_at)
            return result
        if llm.provider == "mock":
            result = _fallback(schema_name, "PRIMARY_LLM_MOCK_PROVIDER", "primary LLM mock provider has no generation")
            self._record_preflight_fallback(schema_name, "PRIMARY_LLM_MOCK_PROVIDER", request_started_at)
            return result
        if not llm.model or not llm.base_url:
            result = _fallback(schema_name, "PRIMARY_LLM_CONFIG_ERROR", "primary LLM model and base_url must be configured")
            self._record_preflight_fallback(schema_name, "PRIMARY_LLM_CONFIG_ERROR", request_started_at)
            return result
        api_key = self._api_key()
        if not api_key:
            payload = _fallback(schema_name, "PRIMARY_LLM_API_KEY_MISSING", "primary LLM API key environment variable is missing")
            payload["api_key_env"] = llm.api_key_env
            self._record_preflight_fallback(schema_name, "PRIMARY_LLM_API_KEY_MISSING", request_started_at)
            return payload

        url = llm.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": llm.model,
            "messages": self._messages(request),
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        attempts = max(1, int(llm.max_retries) + 1)
        overall_started_at = time.perf_counter()
        last_error: str | None = None
        for _ in range(attempts):
            started_at = time.perf_counter()
            raw: dict[str, Any] | None = None
            try:
                raw = await asyncio.to_thread(self.transport, url, payload, headers, float(llm.timeout_seconds))
                content = parse_local_json_response(_extract_chat_content(raw), schema_name)
                content.setdefault("provider", llm.provider)
                content.setdefault("model", llm.model)
                content.setdefault("latency_ms", _latency_ms(started_at))
                status = (
                    "error"
                    if content.get("status") == "error"
                    else "fallback"
                    if content.get("fallback_required") is True
                    else "success"
                )
                self._telemetry.record(
                    schema_name=schema_name,
                    provider=llm.provider,
                    model=llm.model,
                    status=status,
                    latency_ms=int(content["latency_ms"]),
                    usage=chat_completions_usage(raw.get("usage")),
                    fallback_reason=_safe_fallback_reason(content, status),
                )
                return content
            except Exception as exc:
                last_error = exc.__class__.__name__
                usage = (
                    chat_completions_usage(raw.get("usage"))
                    if isinstance(raw, dict)
                    else unavailable_usage()
                )
                self._telemetry.record(
                    schema_name=schema_name,
                    provider=llm.provider,
                    model=llm.model,
                    status="error",
                    latency_ms=_latency_ms(started_at),
                    usage=usage,
                    fallback_reason="PRIMARY_LLM_TRANSPORT_ERROR",
                )
        result = _fallback(schema_name, "PRIMARY_LLM_HTTP_ERROR", last_error or "primary LLM request failed")
        result["provider"] = llm.provider
        result["model"] = llm.model
        result["latency_ms"] = _latency_ms(overall_started_at)
        return result

    def _record_preflight_fallback(self, schema_name: str, reason: str, started_at: float) -> None:
        llm = self.settings.primary_llm
        self._telemetry.record(
            schema_name=schema_name,
            provider=llm.provider,
            model=llm.model or "unknown",
            status="fallback",
            latency_ms=_latency_ms(started_at),
            usage=unavailable_usage(),
            fallback_reason=reason,
        )

    def _api_key(self) -> str | None:
        return resolve_primary_llm_api_key(self.settings)

    def _messages(self, request: PrimaryLLMRequest) -> list[dict[str, str]]:
        system = request.system_prompt or "Return exactly one JSON object. Do not include prose."
        user = request.prompt
        if request.context:
            user = f"{user}\n\nContext JSON:\n{json.dumps(request.context, ensure_ascii=False, sort_keys=True)}"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("primary LLM response must be a JSON object")
    return parsed


def _extract_chat_content(raw: dict[str, Any]) -> str:
    choices = raw.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    if isinstance(raw.get("content"), str):
        return raw["content"]
    return json.dumps(raw, ensure_ascii=False)


def _fallback(schema_name: str, error_code: str, reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "schema_name": schema_name,
        "fallback_required": True,
        "error_code": error_code,
        "reason": reason,
    }


def _latency_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


def _safe_fallback_reason(content: dict[str, Any], status: str) -> str | None:
    if status == "error":
        return "PRIMARY_LLM_ERROR"
    if status == "fallback":
        return "PRIMARY_LLM_FALLBACK"
    return None


def resolve_primary_llm_api_key(settings: Settings) -> str | None:
    env_name = settings.primary_llm.api_key_env
    if not env_name:
        return None
    value = os.getenv(env_name)
    if value:
        return value
    repo_path = settings.rag_server.repo_path
    if not repo_path:
        return None
    return _read_dotenv_value(Path(repo_path) / ".env", env_name)


def _read_dotenv_value(path: Path, env_name: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name.removeprefix("export ").strip()
        if name != env_name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value or None
    return None
