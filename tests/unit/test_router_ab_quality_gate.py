from __future__ import annotations

from backend.app.evaluation.router_ab_quality_gate import (
    evaluate_router_ab_quality_gate,
)


def _report(*, evidence_kind: str = "real", on_success: float = 1.0) -> dict:
    return {
        "evidence_kind": evidence_kind,
        "performance_claim_allowed": evidence_kind == "real",
        "claim_eligibility": {
            "task_success": evidence_kind == "real",
            "latency": evidence_kind == "real",
            "tokens": evidence_kind == "real",
            "cost": evidence_kind == "real",
        },
        "benchmark_context": {
            "rag_preflight_status": "passed",
            "warmup_runs": 1,
            "measured_repeats": 3,
        },
        "metrics": {
            "by_scenario": {
                "router_off": {
                    "task_success_rate": 1.0,
                    "primary_reasoning_success_call_count": 3,
                    "actual_rag_call_count": 3,
                    "high_risk_local_call_count": 0,
                    "s4_actual_rag_call_count": 0,
                },
                "router_shadow": {
                    "task_success_rate": 1.0,
                    "primary_reasoning_success_call_count": 3,
                    "local_success_call_count": 3,
                    "actual_rag_call_count": 3,
                    "high_risk_local_call_count": 0,
                    "s4_actual_rag_call_count": 0,
                },
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
                    "primary_reasoning_success_call_count": 3,
                    "local_takeover_accepted_count": 3,
                    "s4_actual_rag_call_count": 0,
                    "actual_rag_call_count": 3,
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

    with pytest.raises(ValueError, match="real evidence requires a real MCP RAG client"):
        AgentRuntimeEvalRunner(evidence_kind="real")


def test_agent_runtime_rejects_real_label_without_primary_credentials(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    import pytest

    from backend.app.core.config import Settings
    from backend.app.evaluation.agent_runtime_runner import AgentRuntimeEvalRunner
    from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient

    monkeypatch.delenv("ROUTER_TEST_PRIMARY_KEY", raising=False)
    settings = Settings(
        rag_server={"query_mode": "real", "repo_path": str(tmp_path)},
        local_model={"enabled": True, "provider": "transformers", "model": "qwen-test"},
        primary_llm={
            "enabled": True,
            "provider": "openai",
            "model": "primary-test",
            "api_key_env": "ROUTER_TEST_PRIMARY_KEY",
        },
    )

    with pytest.raises(ValueError, match="configured primary model credentials"):
        AgentRuntimeEvalRunner(
            rag_client=RagServerMcpClient(settings),
            evidence_kind="real",
            base_settings=settings,
            warmup_runs=1,
            measured_repeats=3,
        )


def test_router_ab_quality_gate_rejects_real_report_without_claim_eligibility() -> None:
    report = _report()
    report["performance_claim_allowed"] = False

    result = evaluate_router_ab_quality_gate(report)

    assert result.status == "not_eligible"


def test_router_ab_quality_gate_rejects_unverified_real_runtime() -> None:
    report = _report()
    report["benchmark_context"]["rag_preflight_status"] = "not_run"
    report["metrics"]["by_scenario"]["router_off"]["primary_reasoning_success_call_count"] = 0
    report["metrics"]["by_scenario"]["router_shadow"]["local_success_call_count"] = 0
    report["metrics"]["by_scenario"]["router_on"]["local_takeover_accepted_count"] = 0
    report["metrics"]["by_scenario"]["router_on"]["s4_actual_rag_call_count"] = 1

    result = evaluate_router_ab_quality_gate(report)

    assert result.passed is False
    assert "real RAG preflight did not pass" in result.reasons
    assert "router_off primary reasoning success is missing" in result.reasons
    assert "router_shadow local triage success is missing" in result.reasons
    assert "router_on accepted local takeover is missing" in result.reasons
    assert "router_on S4 actual RAG call count 1 > 0" in result.reasons


def test_router_ab_quality_gate_rejects_incomplete_token_or_cost_evidence() -> None:
    report = _report()
    report["claim_eligibility"]["tokens"] = False
    report["claim_eligibility"]["cost"] = False
    report["performance_claim_allowed"] = False

    result = evaluate_router_ab_quality_gate(report)

    assert result.status == "not_eligible"
    assert "complete token and cost evidence is required" in result.reasons


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


def test_router_ab_quality_gate_rejects_equal_failures_across_all_scenarios() -> None:
    report = _report()
    for scenario in report["metrics"]["by_scenario"].values():
        scenario["task_success_rate"] = 0.5

    result = evaluate_router_ab_quality_gate(report)

    assert result.passed is False
    assert "router_off task_success_rate 0.5 < 1.0" in result.reasons
    assert "router_shadow task_success_rate 0.5 < 1.0" in result.reasons
    assert "router_on task_success_rate 0.5 < 1.0" in result.reasons


def test_router_ab_quality_gate_rejects_s4_rag_call_in_any_scenario() -> None:
    report = _report()
    report["metrics"]["by_scenario"]["router_shadow"]["s4_actual_rag_call_count"] = 1

    result = evaluate_router_ab_quality_gate(report)

    assert "router_shadow S4 actual RAG call count 1 > 0" in result.reasons
