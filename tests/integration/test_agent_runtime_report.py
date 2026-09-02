from __future__ import annotations

from backend.app.evaluation.agent_runtime_report import build_agent_runtime_report
from backend.app.evaluation.agent_runtime_runner import (
    AgentRuntimeCaseResult,
    AgentRuntimeEvaluationReport,
)


def test_build_agent_runtime_report_summarizes_route_safety_memory_and_fallback() -> None:
    report = AgentRuntimeEvaluationReport(
        scenarios=["router_shadow", "router_on"],
        metrics={},
        cases=[
            AgentRuntimeCaseResult(
                case_id="C1",
                category="general_qa",
                scenario="router_shadow",
                passed=True,
                checks={"intent": True, "safety": True},
                intent="general_qa",
                route_mode="shadow",
                selected_model="primary",
                end_to_end_latency_ms=30,
                model_latency_ms=20,
                tokens_complete=True,
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                cost_complete=True,
                total_cost_usd=0.01,
            ),
            AgentRuntimeCaseResult(
                case_id="C2",
                category="measurement_analysis",
                scenario="router_on",
                passed=True,
                checks={"intent": True, "safety": True},
                intent="measurement_analysis",
                route_mode="takeover",
                selected_model="local_small",
                tools_used=["body_measurement_analyzer", "long_term_memory"],
                end_to_end_latency_ms=10,
                model_latency_ms=5,
                tokens_complete=False,
                known_input_tokens=2,
                known_output_tokens=1,
                known_total_tokens=3,
                cost_complete=False,
                known_total_cost_usd=0.0,
                local_takeover=True,
            ),
            AgentRuntimeCaseResult(
                case_id="C3",
                category="disease_consultation",
                scenario="router_on",
                passed=False,
                checks={"intent": True, "safety": False},
                intent="disease_consultation",
                route_mode="primary",
                selected_model="primary",
                end_to_end_latency_ms=20,
                model_latency_ms=10,
                fallback_used=True,
                primary_escalation=True,
            ),
        ],
    )

    agent_runtime_report = build_agent_runtime_report(report)
    markdown = agent_runtime_report.to_markdown()

    assert agent_runtime_report.summary["total_cases"] == 3
    assert agent_runtime_report.summary["failed_cases"] == 1
    assert agent_runtime_report.summary["evidence_kind"] == "scripted"
    assert agent_runtime_report.summary["performance_claim_allowed"] is False
    assert agent_runtime_report.route["route_mode_counts"] == {"shadow": 1, "takeover": 1, "primary": 1}
    assert agent_runtime_report.safety["safety_pass_rate"] == 0.6667
    assert agent_runtime_report.memory["memory_write_cases"] == 1
    assert agent_runtime_report.fallback["failed_case_refs"] == ["router_on:C3"]
    assert agent_runtime_report.performance["end_to_end_latency_ms"]["p50"] == 20
    assert agent_runtime_report.performance["end_to_end_latency_ms"]["p95"] == 29
    assert agent_runtime_report.performance["tokens_complete"] is False
    assert agent_runtime_report.performance["total_tokens"] is None
    assert "## Route" in markdown
    assert "## Safety" in markdown
    assert "## Memory" in markdown
    assert "## Fallback" in markdown
