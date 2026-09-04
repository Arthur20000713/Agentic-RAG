from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from backend.app.agent.router import IntentRouter
from backend.app.agent.safety_precheck import SafetyPrecheck, SafetyPrecheckResult
from backend.app.core.config import Settings
from backend.app.model.base import BaseModelClient
from backend.app.model.local_client import LocalModelClient
from backend.app.model.router import ModelRouteDecision, ModelRouter, ModelRouteRequest
from backend.app.schemas.model_routing import LivestockTriageResult, TriageSlot

MIN_TRIAGE_CONFIDENCE = 0.7
ALLOWED_TRIAGE_SLOT_NAMES = {
    "species",
    "age_stage",
    "duration_days",
    "temperature_c",
    "temperature_status",
    "appetite_status",
    "feces_status",
    "respiratory_status",
    "group_outbreak",
}
RISK_RANK = {"low": 0, "medium": 1, "high": 2, "emergency": 3}
MINIMUM_RISK_BY_SAFETY_LEVEL = {"S0": "low", "S1": "low", "S2": "medium", "S3": "high", "S4": "emergency"}
NEGATION_MARKERS = ("no", "not", "without", "none", "没有", "无", "未")
CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_INTEGER_PATTERN = re.compile(r"[零〇一二两三四五六七八九十]+")


class LivestockTriageOutcome(BaseModel):
    """A compact, checkpoint-safe result; raw model payloads and prompts are never retained."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "fallback", "not_run"]
    triage: LivestockTriageResult | None = None
    route_decision: ModelRouteDecision
    fallback_reason: str | None = None


class _TriageTransportEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["success", "error", "unsupported"]
    schema_name: Literal["livestock_triage"]
    fallback_required: StrictBool = False


class LivestockTriage:
    """Run one guarded local intent/slot/risk classification for a trusted user message."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: BaseModelClient | None = None,
        safety_precheck: SafetyPrecheck | None = None,
        intent_router: IntentRouter | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.client = client or LocalModelClient(self.settings)
        self.safety_precheck = safety_precheck or SafetyPrecheck()
        self.intent_router = intent_router or IntentRouter()

    async def run(self, user_query: str) -> LivestockTriageOutcome:
        safety = self.safety_precheck.classify(user_query)
        request = ModelRouteRequest(
            task_type="livestock_triage",
            safety_level=safety.level,
            user_query=user_query,
            metadata={"component": "livestock_triage"},
        )
        decision = ModelRouter(self.settings).route(request)
        if not _can_run_local_triage(decision):
            return LivestockTriageOutcome(
                status="not_run",
                route_decision=decision,
                fallback_reason=decision.blocked_reason or "local_triage_not_selected",
            )

        try:
            raw = await self.client.generate_json(
                user_query,
                schema_name="livestock_triage",
                context={"user_query": user_query},
            )
        except Exception as exc:  # noqa: BLE001 - model adapters must fail closed.
            return _fallback(decision, f"model_error:{exc.__class__.__name__}")

        return _validate_response(raw, user_query=user_query, safety=safety, decision=decision, rule_intent=self.intent_router.route(user_query).intent)


def _can_run_local_triage(decision: ModelRouteDecision) -> bool:
    return decision.selected_model == "local_small" or decision.shadow_model == "local_small"


def _validate_response(
    raw: dict[str, Any],
    *,
    user_query: str,
    safety: SafetyPrecheckResult,
    decision: ModelRouteDecision,
    rule_intent: str,
) -> LivestockTriageOutcome:
    try:
        envelope = _TriageTransportEnvelope.model_validate(raw)
    except ValidationError:
        return _fallback(decision, "transport_schema_invalid")
    if envelope.status != "success" or envelope.fallback_required:
        error_code = raw.get("error_code")
        return _fallback(decision, str(error_code) if isinstance(error_code, str) else "model_requested_fallback")

    fields = LivestockTriageResult.model_fields
    try:
        triage = LivestockTriageResult.model_validate({name: raw.get(name) for name in fields})
    except ValidationError:
        return _fallback(decision, "triage_schema_invalid")

    if triage.confidence < MIN_TRIAGE_CONFIDENCE:
        return _fallback(decision, "triage_confidence_below_threshold")
    if _downgrades_rule_intent(rule_intent, triage.intent_candidate):
        return _fallback(decision, "intent_candidate_downgrades_rule")
    if RISK_RANK[triage.risk_candidate] < RISK_RANK[MINIMUM_RISK_BY_SAFETY_LEVEL[safety.level]]:
        return _fallback(decision, "risk_candidate_downgrades_safety")

    for slot in triage.slots:
        reason = _validate_slot(slot, user_query)
        if reason:
            return _fallback(decision, reason)
    return LivestockTriageOutcome(status="accepted", triage=triage, route_decision=decision)


def _validate_slot(slot: TriageSlot, user_query: str) -> str | None:
    if slot.name not in ALLOWED_TRIAGE_SLOT_NAMES:
        return "slot_name_not_allowed"
    if slot.source_span not in user_query:
        return "slot_span_not_in_query"
    if not _value_is_grounded(slot.value, slot.source_span):
        return "slot_value_not_in_span"
    return None


def _value_is_grounded(value: str | float | bool, source_span: str) -> bool:
    normalized_span = source_span.casefold()
    if isinstance(value, bool):
        is_negative = any(marker in normalized_span for marker in NEGATION_MARKERS)
        return is_negative is (not value)
    if isinstance(value, (int, float)):
        number = re.escape(str(value))
        if re.search(rf"(?<![0-9.]){number}(?![0-9.])", normalized_span):
            return True
        numeric_value = float(value)
        if not numeric_value.is_integer():
            return False
        return any(
            _parse_chinese_integer(token) == int(numeric_value)
            for token in CHINESE_INTEGER_PATTERN.findall(source_span)
        )
    return value.casefold() in normalized_span


def _parse_chinese_integer(text: str) -> int | None:
    if "十" not in text:
        return CHINESE_DIGITS.get(text)
    left, right = text.split("十", 1)
    tens = CHINESE_DIGITS.get(left, 1 if not left else -1)
    ones = CHINESE_DIGITS.get(right, 0 if not right else -1)
    return tens * 10 + ones if tens >= 0 and ones >= 0 else None


def _downgrades_rule_intent(rule_intent: str, candidate: str) -> bool:
    if rule_intent == "disease_consultation":
        return candidate != "disease_consultation"
    return rule_intent in {"general_qa", "measurement_analysis"} and candidate in {"assistant_intro", "out_of_scope"}


def _fallback(decision: ModelRouteDecision, reason: str) -> LivestockTriageOutcome:
    return LivestockTriageOutcome(status="fallback", route_decision=decision, fallback_reason=reason)


def takeover_triage_context(outcome: LivestockTriageOutcome | None) -> dict[str, Any] | None:
    if (
        outcome is None
        or outcome.status != "accepted"
        or outcome.triage is None
        or outcome.route_decision.route_mode != "takeover"
    ):
        return None
    return {
        "intent_candidate": outcome.triage.intent_candidate,
        "slots": [slot.model_dump(mode="json") for slot in outcome.triage.slots],
        "risk_candidate": outcome.triage.risk_candidate,
    }


__all__ = ["LivestockTriage", "LivestockTriageOutcome", "takeover_triage_context"]
