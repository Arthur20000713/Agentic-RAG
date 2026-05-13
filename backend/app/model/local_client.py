from __future__ import annotations

from typing import Any

from backend.app.model.base import BaseModelClient


class LocalModelClient(BaseModelClient):
    provider = "mock"

    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_schema = schema_name.strip().lower()
        if normalized_schema == "final_answer":
            return {
                "status": "unsupported",
                "schema_name": normalized_schema,
                "fallback_required": True,
                "reason": "local model client only supports structured JSON tasks",
            }
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

    def _detect_language(self, text: str) -> str:
        return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"
