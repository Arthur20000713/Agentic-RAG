from __future__ import annotations

import asyncio
from typing import Any

from backend.app.model.base import BaseModelClient
from backend.app.model.query_normalizer import QueryNormalizationPayload, QueryNormalizationResult, normalize_query


class InvalidSchemaClient(BaseModelClient):
    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"status": "success", "normalized_query": "", "language": "invalid"}


class FallbackClient(BaseModelClient):
    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "success",
            "normalized_query": prompt.strip(),
            "language": "en",
            "fallback_required": True,
        }


class RaisingClient(BaseModelClient):
    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError("model unavailable")


def test_normalize_query_returns_valid_schema_from_local_client() -> None:
    result = asyncio.run(normalize_query("  Calf feeding after weaning  "))

    assert isinstance(result, QueryNormalizationResult)
    assert result.normalized_query == "Calf feeding after weaning"
    assert result.language == "en"
    assert result.fallback_used is False
    assert result.warnings == []


def test_query_normalization_payload_schema_accepts_valid_output() -> None:
    payload = QueryNormalizationPayload.model_validate(
        {
            "status": "success",
            "normalized_query": "Calf feeding",
            "language": "en",
            "fallback_required": False,
        }
    )

    assert payload.normalized_query == "Calf feeding"


def test_normalize_query_falls_back_when_schema_is_invalid() -> None:
    result = asyncio.run(normalize_query("  Calf feeding  ", client=InvalidSchemaClient()))

    assert result.normalized_query == "Calf feeding"
    assert result.language == "en"
    assert result.fallback_used is True
    assert result.warnings == ["schema_validation_failed"]


def test_normalize_query_falls_back_when_model_requests_fallback() -> None:
    result = asyncio.run(normalize_query("  Calf feeding  ", client=FallbackClient()))

    assert result.normalized_query == "Calf feeding"
    assert result.fallback_used is True
    assert result.warnings == ["model_requested_fallback"]


def test_normalize_query_falls_back_when_model_raises() -> None:
    result = asyncio.run(normalize_query("犊牛断奶后怎么饲喂？", client=RaisingClient()))

    assert result.normalized_query == "犊牛断奶后怎么饲喂？"
    assert result.language == "zh"
    assert result.fallback_used is True
    assert result.warnings == ["model_error:RuntimeError"]
