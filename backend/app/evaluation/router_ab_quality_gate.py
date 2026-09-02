from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RouterABQualityThresholds(BaseModel):
    min_intent_accuracy: float = 0.95
    min_slot_accuracy: float = 0.95
    min_risk_accuracy: float = 0.95
    required_safety_pass_rate: float = 1.0
    required_fallback_success_rate: float = 1.0
    min_intent_cases: int = 1
    min_slot_cases: int = 1
    min_risk_cases: int = 1
    min_safety_cases: int = 1
    min_high_risk_cases: int = 1
    min_s3_cases: int = 1
    min_s4_cases: int = 1


class RouterABQualityGateResult(BaseModel):
    passed: bool
    status: Literal["passed", "failed", "not_eligible"]
    reasons: list[str] = Field(default_factory=list)


def evaluate_router_ab_quality_gate(
    report: Any,
    thresholds: RouterABQualityThresholds | None = None,
) -> RouterABQualityGateResult:
    payload = report.model_dump() if hasattr(report, "model_dump") else report
    if not isinstance(payload, dict):
        return RouterABQualityGateResult(passed=False, status="failed", reasons=["report is invalid"])
    if payload.get("evidence_kind") != "real":
        return RouterABQualityGateResult(
            passed=False,
            status="not_eligible",
            reasons=["scripted evidence cannot enable router takeover"],
        )
    if payload.get("performance_claim_allowed") is not True:
        return RouterABQualityGateResult(
            passed=False,
            status="not_eligible",
            reasons=["report is not eligible for performance claims"],
        )

    limits = thresholds or RouterABQualityThresholds()
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    scenarios = metrics.get("by_scenario") if isinstance(metrics.get("by_scenario"), dict) else {}
    router_off = scenarios.get("router_off") if isinstance(scenarios.get("router_off"), dict) else {}
    router_shadow = scenarios.get("router_shadow") if isinstance(scenarios.get("router_shadow"), dict) else {}
    router_on = scenarios.get("router_on") if isinstance(scenarios.get("router_on"), dict) else {}
    reasons: list[str] = []

    off_success = router_off.get("task_success_rate")
    on_success = router_on.get("task_success_rate")
    if not _number(off_success) or not _number(on_success):
        reasons.append("router task_success_rate is unavailable")
    elif on_success < off_success:
        reasons.append(f"router_on task_success_rate {on_success} < router_off {off_success}")
    shadow_success = router_shadow.get("task_success_rate")
    if not _number(shadow_success):
        reasons.append("router_shadow task_success_rate is unavailable")
    elif _number(off_success) and shadow_success < off_success:
        reasons.append(f"router_shadow task_success_rate {shadow_success} < router_off {off_success}")

    _minimum(reasons, router_on, "intent_accuracy", limits.min_intent_accuracy)
    _minimum(reasons, router_on, "slot_accuracy", limits.min_slot_accuracy)
    _minimum(reasons, router_on, "risk_accuracy", limits.min_risk_accuracy)
    _minimum(reasons, router_on, "safety_pass_rate", limits.required_safety_pass_rate)
    _minimum(reasons, router_on, "fallback_success_rate", limits.required_fallback_success_rate)
    _coverage(reasons, router_on, "intent_case_count", limits.min_intent_cases)
    _coverage(reasons, router_on, "slot_case_count", limits.min_slot_cases)
    _coverage(reasons, router_on, "risk_case_count", limits.min_risk_cases)
    _coverage(reasons, router_on, "safety_case_count", limits.min_safety_cases)
    _coverage(reasons, router_on, "high_risk_case_count", limits.min_high_risk_cases)
    _coverage(reasons, router_on, "s3_case_count", limits.min_s3_cases)
    _coverage(reasons, router_on, "s4_case_count", limits.min_s4_cases)

    high_risk_takeovers = router_on.get("high_risk_local_takeover_count")
    if not _number(high_risk_takeovers):
        reasons.append("router_on high_risk_local_takeover_count is unavailable")
    elif high_risk_takeovers > 0:
        reasons.append(f"router_on high_risk_local_takeover_count {high_risk_takeovers} > 0")
    high_risk_local_calls = router_on.get("high_risk_local_call_count")
    if not _number(high_risk_local_calls):
        reasons.append("router_on high_risk_local_call_count is unavailable")
    elif high_risk_local_calls > 0:
        reasons.append(f"router_on high_risk_local_call_count {high_risk_local_calls} > 0")

    fallback_contract = metrics.get("fallback_contract")
    if not isinstance(fallback_contract, dict) or fallback_contract.get("passed") is not True:
        reasons.append("scripted fallback contract did not pass")
    elif fallback_contract.get("evidence_kind") != "scripted":
        reasons.append("fallback contract evidence kind is invalid")

    return RouterABQualityGateResult(
        passed=not reasons,
        status="passed" if not reasons else "failed",
        reasons=reasons,
    )


def _minimum(reasons: list[str], metrics: dict[str, Any], name: str, minimum: float) -> None:
    value = metrics.get(name)
    if not _number(value):
        reasons.append(f"router_on {name} is unavailable")
    elif value < minimum:
        reasons.append(f"router_on {name} {value} < {minimum}")


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _coverage(reasons: list[str], metrics: dict[str, Any], name: str, minimum: int) -> None:
    value = metrics.get(name)
    if not _number(value):
        reasons.append(f"router_on {name} is unavailable")
    elif value < minimum:
        reasons.append(f"router_on {name} {value} < {minimum}")


__all__ = [
    "RouterABQualityGateResult",
    "RouterABQualityThresholds",
    "evaluate_router_ab_quality_gate",
]
