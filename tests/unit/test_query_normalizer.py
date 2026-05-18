from __future__ import annotations

import asyncio
from typing import Any

from backend.app.core.config import Settings
from backend.app.model.base import BaseModelClient
from backend.app.model.query_normalizer import (
    QueryNormalizationPayload,
    QueryNormalizationResult,
    normalize_query,
    normalize_query_with_router,
)


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


class LocalRewriteClient(BaseModelClient):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((prompt, schema_name))
        return self.payload


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


def test_normalize_query_with_router_uses_local_output_in_takeover_mode() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["query_normalization"],
        },
        local_model={"enabled": True},
    )
    client = LocalRewriteClient(
        {
            "status": "success",
            "normalized_query": "calf weaning feeding",
            "language": "en",
            "fallback_required": False,
        }
    )

    result = asyncio.run(normalize_query_with_router("Calf after weaning", settings=settings, client=client))

    assert result.normalized_query == "calf weaning feeding"
    assert result.fallback_used is False
    assert result.route_mode == "takeover"
    assert result.selected_model == "local_small"
    assert client.calls == [("Calf after weaning", "query_normalization")]


def test_normalize_query_with_router_keeps_primary_result_in_shadow_mode() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={
            "enabled": True,
            "shadow_mode": True,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["query_normalization"],
        },
        local_model={"enabled": True},
    )
    client = LocalRewriteClient(
        {
            "status": "success",
            "normalized_query": "local shadow output",
            "language": "en",
            "fallback_required": False,
        }
    )

    result = asyncio.run(normalize_query_with_router("  Calf after weaning  ", settings=settings, client=client))

    assert result.normalized_query == "Calf after weaning"
    assert result.fallback_used is False
    assert result.route_mode == "shadow"
    assert result.selected_model == "primary"
    assert client.calls == []


def test_normalize_query_with_router_falls_back_when_local_schema_invalid() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["query_normalization"],
        },
        local_model={"enabled": True},
    )

    result = asyncio.run(
        normalize_query_with_router("  Calf after weaning  ", settings=settings, client=InvalidSchemaClient())
    )

    assert result.normalized_query == "Calf after weaning"
    assert result.fallback_used is True
    assert result.route_mode == "takeover"
    assert result.fallback_reason == "schema_validation_failed"
