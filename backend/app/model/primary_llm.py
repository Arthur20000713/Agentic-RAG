from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.app.core.config import Settings
from backend.app.model.local_schema import parse_local_json_response


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

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        llm = self.settings.primary_llm
        schema_name = request.schema_name.strip().lower()
        if not llm.enabled:
            return _fallback(schema_name, "PRIMARY_LLM_DISABLED", "primary LLM is disabled")
        if llm.provider == "mock":
            return _fallback(schema_name, "PRIMARY_LLM_MOCK_PROVIDER", "primary LLM mock provider has no generation")
        if not llm.model or not llm.base_url:
            return _fallback(schema_name, "PRIMARY_LLM_CONFIG_ERROR", "primary LLM model and base_url must be configured")
        api_key = self._api_key()
        if not api_key:
            payload = _fallback(schema_name, "PRIMARY_LLM_API_KEY_MISSING", "primary LLM API key environment variable is missing")
            payload["api_key_env"] = llm.api_key_env
            return payload

        started_at = time.perf_counter()
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
        last_error: str | None = None
        for _ in range(attempts):
            try:
                raw = await asyncio.to_thread(self.transport, url, payload, headers, float(llm.timeout_seconds))
                content = parse_local_json_response(_extract_chat_content(raw), schema_name)
                content.setdefault("provider", llm.provider)
                content.setdefault("model", llm.model)
                content.setdefault("latency_ms", _latency_ms(started_at))
                return content
            except Exception as exc:
                last_error = str(exc) or exc.__class__.__name__
        result = _fallback(schema_name, "PRIMARY_LLM_HTTP_ERROR", last_error or "primary LLM request failed")
        result["provider"] = llm.provider
        result["model"] = llm.model
        result["latency_ms"] = _latency_ms(started_at)
        return result

    def _api_key(self) -> str | None:
        env_name = self.settings.primary_llm.api_key_env
        if not env_name:
            return None
        value = os.getenv(env_name)
        return value if value else None

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
