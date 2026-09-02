from __future__ import annotations

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


class LocalModelClient(BaseModelClient):
    provider = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.provider = self.settings.local_model.provider
        self._backend_cache: dict[str, BaseLocalBackend] = {}

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
        if normalized_schema in PRIMARY_ONLY_SCHEMA_NAMES:
            return {
                "status": "unsupported",
                "schema_name": normalized_schema,
                "fallback_required": True,
                "reason": "local model may not execute primary-only schema",
            }

        if self.provider == "mock":
            return self._generate_mock_json(prompt, normalized_schema, context)

        endpoint = self.settings.local_model.endpoint
        model = self.settings.local_model.model
        if not model or (self.provider != "transformers" and not endpoint):
            return self._fallback(
                normalized_schema,
                error_code="LOCAL_MODEL_CONFIG_ERROR",
                reason=self._config_error_reason(),
            )

        backend = self._select_backend()
        if backend is None:
            return self._fallback(
                normalized_schema,
                error_code="LOCAL_MODEL_PROVIDER_UNSUPPORTED",
                reason=f"unsupported local model provider: {self.provider}",
            )
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
