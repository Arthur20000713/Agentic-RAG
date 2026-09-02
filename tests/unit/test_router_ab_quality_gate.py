from __future__ import annotations

from backend.app.evaluation.router_ab_quality_gate import (
    evaluate_router_ab_quality_gate,
)


def _report(*, evidence_kind: str = "real", on_success: float = 1.0) -> dict:
    return {
        "evidence_kind": evidence_kind,
        "performance_claim_allowed": evidence_kind == "real",
        "metrics": {
            "by_scenario": {
                "router_off": {"task_success_rate": 1.0},
                "router_shadow": {"task_success_rate": 1.0},
                "router_on": {
                    "task_success_rate": on_success,
                    "intent_accuracy": 1.0,
                    "slot_accuracy": 1.0,
                    "risk_accuracy": 1.0,
                    "safety_pass_rate": 1.0,
                    "high_risk_local_takeover_count": 0,
                    "fallback_success_rate": 1.0,
                    "intent_case_count": 10,
                    "slot_case_count": 8,
                    "risk_case_count": 8,
                    "safety_case_count": 10,
                    "high_risk_case_count": 2,
                    "s3_case_count": 1,
                    "s4_case_count": 1,
                    "high_risk_local_call_count": 0,
                },
            },
            "fallback_contract": {"passed": True, "evidence_kind": "scripted"},
        },
    }


def test_router_ab_quality_gate_accepts_eligible_real_report() -> None:
    result = evaluate_router_ab_quality_gate(_report())

    assert result.passed is True
    assert result.status == "passed"
    assert result.reasons == []


def test_router_ab_quality_gate_rejects_scripted_evidence() -> None:
    result = evaluate_router_ab_quality_gate(_report(evidence_kind="scripted"))

    assert result.passed is False
    assert result.status == "not_eligible"
    assert result.reasons == ["scripted evidence cannot enable router takeover"]


def test_agent_runtime_rejects_real_label_with_fake_rag() -> None:
    import pytest

    from backend.app.evaluation.agent_runtime_runner import AgentRuntimeEvalRunner

    with pytest.raises(ValueError, match="real evidence requires a non-fake RAG client"):
        AgentRuntimeEvalRunner(evidence_kind="real")


def test_router_ab_quality_gate_rejects_real_report_without_claim_eligibility() -> None:
    report = _report()
    report["performance_claim_allowed"] = False

    result = evaluate_router_ab_quality_gate(report)

    assert result.status == "not_eligible"


def test_router_ab_quality_gate_reports_quality_and_safety_regressions() -> None:
    report = _report(on_success=0.8)
    on = report["metrics"]["by_scenario"]["router_on"]
    on["slot_accuracy"] = None
    on["safety_pass_rate"] = 0.9
    on["high_risk_local_takeover_count"] = 1
    on["high_risk_local_call_count"] = 1
    on["fallback_success_rate"] = 0.5

    result = evaluate_router_ab_quality_gate(report)

    assert result.passed is False
    assert "router_on task_success_rate 0.8 < router_off 1.0" in result.reasons
    assert "router_on slot_accuracy is unavailable" in result.reasons
    assert "router_on safety_pass_rate 0.9 < 1.0" in result.reasons
    assert "router_on high_risk_local_takeover_count 1 > 0" in result.reasons
    assert "router_on high_risk_local_call_count 1 > 0" in result.reasons
    assert "router_on fallback_success_rate 0.5 < 1.0" in result.reasons


def test_router_ab_quality_gate_fails_closed_without_required_case_coverage() -> None:
    report = _report()
    on = report["metrics"]["by_scenario"]["router_on"]
    on["slot_case_count"] = 0
    on["high_risk_case_count"] = 0
    report["metrics"]["fallback_contract"]["passed"] = False

    result = evaluate_router_ab_quality_gate(report)

    assert result.passed is False
    assert "router_on slot_case_count 0 < 1" in result.reasons
    assert "router_on high_risk_case_count 0 < 1" in result.reasons
    assert "scripted fallback contract did not pass" in result.reasons


def test_router_ab_quality_gate_rejects_shadow_task_regression() -> None:
    report = _report()
    report["metrics"]["by_scenario"]["router_shadow"]["task_success_rate"] = 0.9

    result = evaluate_router_ab_quality_gate(report)

    assert "router_shadow task_success_rate 0.9 < router_off 1.0" in result.reasons
