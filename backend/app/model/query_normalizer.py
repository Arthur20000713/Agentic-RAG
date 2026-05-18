from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.safety_precheck import SafetyPrecheck
from backend.app.core.config import Settings
from backend.app.model.base import BaseModelClient
from backend.app.model.local_client import LocalModelClient
from backend.app.model.router import ModelRouteRequest, ModelRouter


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
    route_mode: str | None = None
    selected_model: str | None = None
    fallback_reason: str | None = None
    route_request: dict[str, Any] | None = None
    route_decision: dict[str, Any] | None = None


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


async def normalize_query_with_router(
    query: str,
    *,
    settings: Settings | None = None,
    client: BaseModelClient | None = None,
) -> QueryNormalizationResult:
    app_settings = settings or Settings()
    safety = SafetyPrecheck().classify(query)
    route_request = ModelRouteRequest(
        task_type="query_normalization",
        safety_level=safety.level,
        requires_final_answer=False,
        user_query=query,
        metadata={"component": "query_normalization"},
    )
    decision = ModelRouter(app_settings).route(route_request)
    if decision.selected_model != "local_small":
        result = _rule_result(query, fallback_used=False)
        return _attach_route(result, route_request=route_request, route_decision=decision)

    result = await normalize_query(query, client=client or LocalModelClient(app_settings))
    if result.fallback_used and result.warnings:
        result.fallback_reason = result.warnings[-1]
    return _attach_route(result, route_request=route_request, route_decision=decision)


def fallback_with_warning(result: QueryNormalizationResult, warning: str) -> QueryNormalizationResult:
    result.fallback_used = True
    result.warnings.append(warning)
    return result


def _fallback_result(query: str) -> QueryNormalizationResult:
    return _rule_result(query, fallback_used=True)


def _rule_result(query: str, *, fallback_used: bool) -> QueryNormalizationResult:
    stripped = query.strip()
    return QueryNormalizationResult(
        normalized_query=stripped,
        language=_detect_language(stripped),
        fallback_used=fallback_used,
    )


def _attach_route(
    result: QueryNormalizationResult,
    *,
    route_request: ModelRouteRequest,
    route_decision,
) -> QueryNormalizationResult:
    result.route_mode = route_decision.route_mode
    result.selected_model = route_decision.selected_model
    result.route_request = route_request.model_dump()
    result.route_decision = route_decision.model_dump()
    if result.fallback_reason is None:
        result.fallback_reason = route_decision.blocked_reason
    return result


def _detect_language(text: str) -> QueryLanguage:
    if not text:
        return "unknown"
    return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"
