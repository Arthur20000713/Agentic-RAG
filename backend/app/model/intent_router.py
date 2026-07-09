from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.router import IntentRouter
from backend.app.agent.safety_precheck import SafetyPrecheck
from backend.app.core.config import Settings
from backend.app.model.base import BaseModelClient
from backend.app.model.local_client import LocalModelClient
from backend.app.model.router import ModelRouteRequest, ModelRouter
from backend.app.schemas.agent import IntentType


ALLOWED_INTENTS = [
    "assistant_intro",
    "general_qa",
    "disease_consultation",
    "measurement_analysis",
    "out_of_scope",
]
DIRECT_WITHOUT_RAG_INTENTS = {"assistant_intro", "measurement_analysis", "out_of_scope"}
DIRECT_INTENT_GUARD_CONFIDENCE = 0.84


class IntentRoutingPayload(BaseModel):
    status: Literal["success"]
    schema_name: Literal["intent_routing"] = "intent_routing"
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    should_use_rag: bool = True
    should_use_tools: list[str] = Field(default_factory=list)
    reason: str = ""
    fallback_required: bool = False


class IntentRoutingResult(BaseModel):
    intent: IntentType
    confidence: float
    reason: str = ""
    should_use_rag: bool = True
    should_use_tools: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: str | None = None
    route_mode: str | None = None
    selected_model: str | None = None
    route_request: dict[str, Any] | None = None
    route_decision: dict[str, Any] | None = None


async def route_intent_with_model(
    query: str,
    *,
    settings: Settings | None = None,
    client: BaseModelClient | None = None,
    router: IntentRouter | None = None,
    session_context: dict[str, Any] | None = None,
) -> IntentRoutingResult:
    app_settings = settings or Settings()
    safety = SafetyPrecheck().classify(query)
    route_request = ModelRouteRequest(
        task_type="intent_routing",
        safety_level=safety.level,
        requires_final_answer=False,
        user_query=query,
        metadata={"component": "intent_routing"},
    )
    decision = ModelRouter(app_settings).route(route_request)
    rule_result = _rule_result(query, router=router)

    if decision.selected_model != "local_small":
        return _attach_route(rule_result, route_request=route_request, route_decision=decision)

    model_client = client or LocalModelClient(app_settings)
    try:
        raw = await model_client.generate_json(
            _intent_prompt(query),
            schema_name="intent_routing",
            context={
                "allowed_intents": ALLOWED_INTENTS,
                "user_query": query,
                "session_context": session_context or {},
                "safety_level": safety.level,
            },
        )
    except Exception as exc:
        result = _with_fallback(rule_result, f"model_error:{exc.__class__.__name__}")
        return _attach_route(result, route_request=route_request, route_decision=decision)

    try:
        payload = IntentRoutingPayload.model_validate(raw)
    except ValidationError:
        result = _with_fallback(rule_result, "schema_validation_failed")
        return _attach_route(result, route_request=route_request, route_decision=decision)

    if payload.fallback_required:
        result = _with_fallback(rule_result, "model_requested_fallback")
        return _attach_route(result, route_request=route_request, route_decision=decision)

    if _should_guard_direct_intent(rule_result, payload):
        result = _with_fallback(rule_result, "direct_intent_guardrail")
        return _attach_route(result, route_request=route_request, route_decision=decision)

    result = IntentRoutingResult(
        intent=payload.intent,
        confidence=payload.confidence,
        reason=payload.reason,
        should_use_rag=_enforce_rag_policy(payload.intent, payload.should_use_rag),
        should_use_tools=list(payload.should_use_tools),
    )
    return _attach_route(result, route_request=route_request, route_decision=decision)


def _intent_prompt(query: str) -> str:
    return (
        "Classify the user message for a livestock assistant. Return JSON only. "
        "Allowed intents: assistant_intro, general_qa, disease_consultation, measurement_analysis, out_of_scope. "
        "Use disease_consultation for animal symptoms, disease, fever, diarrhea, cough, appetite changes, or health risk. "
        "Use general_qa for livestock management or knowledge questions. "
        "Use assistant_intro only for greeting or asking what the assistant can do. "
        "Use out_of_scope for non-livestock requests. "
        "Set should_use_rag=true for general_qa and disease_consultation. "
        f"User message: {query.strip()}"
    )


def _rule_result(query: str, *, router: IntentRouter | None = None) -> IntentRoutingResult:
    route = (router or IntentRouter()).route(query)
    return IntentRoutingResult(
        intent=route.intent,
        confidence=route.confidence,
        reason=route.reason,
        should_use_rag=_enforce_rag_policy(route.intent, route.intent in {"general_qa", "disease_consultation"}),
        should_use_tools=[],
    )


def _with_fallback(result: IntentRoutingResult, reason: str) -> IntentRoutingResult:
    result.fallback_used = True
    result.fallback_reason = reason
    return result


def _should_guard_direct_intent(rule_result: IntentRoutingResult, payload: IntentRoutingPayload) -> bool:
    if rule_result.intent not in DIRECT_WITHOUT_RAG_INTENTS:
        return False
    if rule_result.confidence < DIRECT_INTENT_GUARD_CONFIDENCE:
        return False
    return payload.intent != rule_result.intent or payload.should_use_rag


def _attach_route(
    result: IntentRoutingResult,
    *,
    route_request: ModelRouteRequest,
    route_decision,
) -> IntentRoutingResult:
    result.route_mode = route_decision.route_mode
    result.selected_model = route_decision.selected_model
    result.route_request = route_request.model_dump()
    result.route_decision = route_decision.model_dump()
    if result.fallback_reason is None:
        result.fallback_reason = route_decision.blocked_reason
    return result


def _enforce_rag_policy(intent: IntentType, requested: bool) -> bool:
    if intent in DIRECT_WITHOUT_RAG_INTENTS:
        return bool(requested)
    if intent in {"general_qa", "disease_consultation"}:
        return True
    return bool(requested)
