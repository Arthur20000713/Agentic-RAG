from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.model.base import BaseModelClient
from backend.app.model.local_client import LocalModelClient


QueryLanguage = Literal["zh", "en", "unknown"]


class QueryNormalizationPayload(BaseModel):
    status: Literal["success"]
    normalized_query: str = Field(min_length=1)
    language: QueryLanguage = "unknown"
    fallback_required: bool = False


class QueryNormalizationResult(BaseModel):
    normalized_query: str
    language: QueryLanguage = "unknown"
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)


async def normalize_query(query: str, *, client: BaseModelClient | None = None) -> QueryNormalizationResult:
    model_client = client or LocalModelClient()
    fallback = _fallback_result(query)
    try:
        raw = await model_client.generate_json(query, schema_name="query_normalization")
    except Exception as exc:
        return fallback_with_warning(fallback, f"model_error:{exc.__class__.__name__}")

    try:
        payload = QueryNormalizationPayload.model_validate(raw)
    except ValidationError:
        return fallback_with_warning(fallback, "schema_validation_failed")

    if payload.fallback_required:
        return fallback_with_warning(fallback, "model_requested_fallback")
    return QueryNormalizationResult(normalized_query=payload.normalized_query, language=payload.language)


def fallback_with_warning(result: QueryNormalizationResult, warning: str) -> QueryNormalizationResult:
    result.fallback_used = True
    result.warnings.append(warning)
    return result


def _fallback_result(query: str) -> QueryNormalizationResult:
    stripped = query.strip()
    return QueryNormalizationResult(
        normalized_query=stripped,
        language=_detect_language(stripped),
        fallback_used=True,
    )


def _detect_language(text: str) -> QueryLanguage:
    if not text:
        return "unknown"
    return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"
