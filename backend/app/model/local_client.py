from __future__ import annotations

import time
from typing import Any

from backend.app.core.config import Settings
from backend.app.lora.dataset import LoraTaskType
from backend.app.lora.inference import select_lora_adapter
from backend.app.lora.registry import ModelRegistry, ModelRegistryEntry
from backend.app.model.base import BaseModelClient
from backend.app.model.local_backends import (
    BaseLocalBackend,
    LocalBackendRequest,
    OllamaBackend,
    TransformersBackend,
)
from backend.app.model.usage import ModelCallRecorder, unavailable_usage
from backend.app.schemas.model_routing import ModelCallRecord

PRIMARY_ONLY_SCHEMA_NAMES = {
    "direct_answer_draft",
    "disease_case_understanding",
    "disease_reasoning",
    "final_answer",
    "grounded_rag_answer",
    "planning",
    "reasoning",
    "reference_only_answer",
    "retrieval_decomposition",
    "retrieval_rewrite",
    "task_plan",
}
SAFE_LOCAL_ERROR_CODES = {
    "LOCAL_MODEL_GENERATION_ERROR",
    "LOCAL_MODEL_HTTP_ERROR",
    "LOCAL_MODEL_IMPORT_ERROR",
    "LOCAL_MODEL_SCHEMA_ERROR",
    "LOCAL_MODEL_SCHEMA_UNSUPPORTED",
    "LOCAL_MODEL_TIMEOUT",
}


class LocalModelClient(BaseModelClient):
    provider = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.provider = self.settings.local_model.provider
        self._backend_cache: dict[str, BaseLocalBackend] = {}
        self._telemetry = ModelCallRecorder(self.settings, "local_small")

    def telemetry_scope(self, operation_prefix: str):
        return self._telemetry.scope(operation_prefix)

    def drain_model_call_records(self) -> list[ModelCallRecord]:
        return self._telemetry.drain()

    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_started_at = time.perf_counter()
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
        if normalized_schema in PRIMARY_ONLY_SCHEMA_NAMES:
            return {
                "status": "unsupported",
                "schema_name": normalized_schema,
                "fallback_required": True,
                "reason": "local model may not execute primary-only schema",
            }

        if self.provider == "mock":
            payload = self._generate_mock_json(prompt, normalized_schema, context)
            self._telemetry.record(
                schema_name=normalized_schema,
                provider=self.provider,
                model=self.settings.local_model.model or "mock",
                status="success",
                latency_ms=max(0, int((time.perf_counter() - request_started_at) * 1000)),
                usage=unavailable_usage(),
            )
            return payload

        endpoint = self.settings.local_model.endpoint
        model = self.settings.local_model.model
        if not model or (self.provider != "transformers" and not endpoint):
            result = self._fallback(
                normalized_schema,
                error_code="LOCAL_MODEL_CONFIG_ERROR",
                reason=self._config_error_reason(),
            )
            self._record_preflight_fallback(normalized_schema, "LOCAL_MODEL_CONFIG_ERROR", request_started_at)
            return result

        backend = self._select_backend()
        if backend is None:
            result = self._fallback(
                normalized_schema,
                error_code="LOCAL_MODEL_PROVIDER_UNSUPPORTED",
                reason=f"unsupported local model provider: {self.provider}",
            )
            self._record_preflight_fallback(normalized_schema, "LOCAL_MODEL_PROVIDER_UNSUPPORTED", request_started_at)
            return result
        adapter = self._select_lora_adapter(normalized_schema)
        options = self._lora_options(adapter)

        response = await backend.generate(
            LocalBackendRequest(
                prompt=prompt,
                schema_name=normalized_schema,
                endpoint=endpoint or "",
                model=model,
                timeout_seconds=self.settings.local_model.timeout_seconds,
                context=context,
                options={**self._local_model_options(), **options},
            )
        )
        payload = dict(response.content)
        payload.setdefault("status", response.status)
        payload.setdefault("schema_name", normalized_schema)
        payload.setdefault("fallback_required", response.fallback_required)
        payload.setdefault("provider", backend.provider)
        payload.setdefault("model", model)
        if adapter is not None:
            payload.setdefault("lora_adapter_id", adapter.model_id)
        if response.error_code:
            payload.setdefault("error_code", response.error_code)
        if response.reason:
            payload.setdefault("reason", response.reason)
        payload.setdefault("latency_ms", response.latency_ms)
        self._telemetry.record(
            schema_name=normalized_schema,
            provider=backend.provider,
            model=model,
            status=(
                "error"
                if response.status == "error"
                else "fallback"
                if response.fallback_required
                else "success"
            ),
            latency_ms=response.latency_ms,
            usage=response.usage,
            fallback_reason=_safe_local_fallback_reason(response),
        )
        return payload

    def _select_backend(self) -> BaseLocalBackend | None:
        if self.provider in self._backend_cache:
            return self._backend_cache[self.provider]
        if self.provider == "ollama":
            self._backend_cache[self.provider] = OllamaBackend()
            return self._backend_cache[self.provider]
        if self.provider == "transformers":
            self._backend_cache[self.provider] = TransformersBackend()
            return self._backend_cache[self.provider]
        return None

    def _record_preflight_fallback(self, schema_name: str, reason: str, started_at: float) -> None:
        self._telemetry.record(
            schema_name=schema_name,
            provider=self.provider,
            model=self.settings.local_model.model or "unknown",
            status="fallback",
            latency_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
            usage=unavailable_usage(),
            fallback_reason=reason,
        )

    def _select_lora_adapter(self, schema_name: str) -> ModelRegistryEntry | None:
        if not self.settings.lora.inference_enabled:
            return None
        task_type = self._schema_to_lora_task(schema_name)
        if task_type is None:
            return None
        return select_lora_adapter(task_type, ModelRegistry(self.settings.lora.registry_path))

    def _schema_to_lora_task(self, schema_name: str) -> LoraTaskType | None:
        if schema_name in {"query_normalization", "slot_extraction", "measurement_formatting"}:
            return schema_name  # type: ignore[return-value]
        return None

    def _lora_options(self, adapter: ModelRegistryEntry | None) -> dict[str, Any]:
        if adapter is None:
            return {}
        return {"lora_adapter": adapter.adapter_path, "lora_model_id": adapter.model_id}

    def _local_model_options(self) -> dict[str, Any]:
        return {
            "device": self.settings.local_model.device,
            "torch_dtype": self.settings.local_model.torch_dtype,
            "max_new_tokens": self.settings.local_model.max_new_tokens,
            "temperature": self.settings.local_model.temperature,
        }

    def _config_error_reason(self) -> str:
        if self.provider == "transformers":
            return "local_model.model must be configured for transformers provider"
        return "local model endpoint and model must be configured"

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
        if normalized_schema == "intent_routing":
            from backend.app.agent.router import IntentRouter

            route_query = str((context or {}).get("user_query") or prompt)
            route = IntentRouter().route(route_query)
            return {
                "status": "success",
                "schema_name": normalized_schema,
                "intent": route.intent,
                "confidence": route.confidence,
                "should_use_rag": route.intent in {"general_qa", "disease_consultation"},
                "should_use_tools": [],
                "reason": route.reason,
                "fallback_required": False,
                "provider": self.provider,
            }
        if normalized_schema == "livestock_triage":
            from backend.app.agent.router import IntentRouter
            from backend.app.agent.safety_precheck import SafetyPrecheck

            route_query = str((context or {}).get("user_query") or prompt)
            route = IntentRouter().route(route_query)
            safety = SafetyPrecheck().classify(route_query)
            risk_by_safety = {
                "S0": "low",
                "S1": "low",
                "S2": "medium",
                "S3": "high",
                "S4": "emergency",
            }
            return {
                "status": "success",
                "schema_name": normalized_schema,
                "intent_candidate": route.intent,
                "confidence": route.confidence,
                "slots": [],
                "risk_candidate": risk_by_safety[safety.level],
                "risk_signals": list(safety.risk_tags),
                "fallback_required": False,
                "provider": self.provider,
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


def _safe_local_fallback_reason(response: LocalBackendResponse) -> str | None:
    if response.error_code in SAFE_LOCAL_ERROR_CODES:
        return response.error_code
    if response.status == "error":
        return "LOCAL_MODEL_ERROR"
    if response.fallback_required:
        return "LOCAL_MODEL_FALLBACK"
    return None
