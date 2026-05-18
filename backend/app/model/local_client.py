from __future__ import annotations

from typing import Any

from backend.app.core.config import Settings
from backend.app.model.base import BaseModelClient
from backend.app.model.local_backends import BaseLocalBackend, LocalBackendRequest, OllamaBackend


class LocalModelClient(BaseModelClient):
    provider = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.provider = self.settings.local_model.provider

    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_schema = schema_name.strip().lower()
        if normalized_schema == "final_answer":
            if self.provider != "mock" and not self.settings.local_model.allow_final_answer:
                return {
                    "status": "unsupported",
                    "schema_name": normalized_schema,
                    "fallback_required": True,
                    "reason": "local model final_answer takeover is disabled",
                }
            return {
                "status": "unsupported",
                "schema_name": normalized_schema,
                "fallback_required": True,
                "reason": "local model client only supports structured JSON tasks",
            }

        if self.provider == "mock":
            return self._generate_mock_json(prompt, normalized_schema, context)

        endpoint = self.settings.local_model.endpoint
        model = self.settings.local_model.model
        if not endpoint or not model:
            return self._fallback(
                normalized_schema,
                error_code="LOCAL_MODEL_CONFIG_ERROR",
                reason="local model endpoint and model must be configured",
            )

        backend = self._select_backend()
        if backend is None:
            return self._fallback(
                normalized_schema,
                error_code="LOCAL_MODEL_PROVIDER_UNSUPPORTED",
                reason=f"unsupported local model provider: {self.provider}",
            )

        response = await backend.generate(
            LocalBackendRequest(
                prompt=prompt,
                schema_name=normalized_schema,
                endpoint=endpoint,
                model=model,
                timeout_seconds=self.settings.local_model.timeout_seconds,
                context=context,
            )
        )
        payload = dict(response.content)
        payload.setdefault("status", response.status)
        payload.setdefault("schema_name", normalized_schema)
        payload.setdefault("fallback_required", response.fallback_required)
        payload.setdefault("provider", backend.provider)
        payload.setdefault("model", model)
        if response.error_code:
            payload.setdefault("error_code", response.error_code)
        if response.reason:
            payload.setdefault("reason", response.reason)
        payload.setdefault("latency_ms", response.latency_ms)
        return payload

    def _select_backend(self) -> BaseLocalBackend | None:
        if self.provider == "ollama":
            return OllamaBackend()
        return None

    def _generate_mock_json(
        self,
        prompt: str,
        normalized_schema: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if normalized_schema == "query_normalization":
            return {
                "status": "success",
                "schema_name": normalized_schema,
                "normalized_query": prompt.strip(),
                "language": self._detect_language(prompt),
                "fallback_required": False,
            }
        return {
            "status": "success",
            "schema_name": normalized_schema,
            "fields": {},
            "confidence": 0.0,
            "fallback_required": False,
            "provider": self.provider,
            "context_keys": sorted((context or {}).keys()),
        }

    def _fallback(self, schema_name: str, *, error_code: str, reason: str) -> dict[str, Any]:
        return {
            "status": "error",
            "schema_name": schema_name,
            "fallback_required": True,
            "provider": self.provider,
            "error_code": error_code,
            "reason": reason,
        }

    def _detect_language(self, text: str) -> str:
        return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"
