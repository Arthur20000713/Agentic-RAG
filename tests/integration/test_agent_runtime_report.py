from __future__ import annotations

from backend.app.evaluation.agent_runtime_report import build_agent_runtime_report
from backend.app.evaluation.agent_runtime_runner import AgentRuntimeCaseResult, AgentRuntimeEvaluationReport


def test_build_agent_runtime_report_summarizes_route_safety_memory_and_fallback() -> None:
    report = AgentRuntimeEvaluationReport(
        scenarios=["router_shadow", "router_low_risk"],
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
            ),
            AgentRuntimeCaseResult(
                case_id="C2",
                category="measurement_analysis",
                scenario="router_low_risk",
                passed=True,
                checks={"intent": True, "safety": True},
                intent="measurement_analysis",
                route_mode="takeover",
                selected_model="local_small",
                tools_used=["body_measurement_analyzer", "long_term_memory"],
            ),
            AgentRuntimeCaseResult(
                case_id="C3",
                category="disease_consultation",
                scenario="router_low_risk",
                passed=False,
                checks={"intent": True, "safety": False},
                intent="disease_consultation",
                route_mode="primary",
                selected_model="primary",
            ),
        ],
    )

    agent_runtime_report = build_agent_runtime_report(report)
    markdown = agent_runtime_report.to_markdown()

    assert agent_runtime_report.summary["total_cases"] == 3
    assert agent_runtime_report.summary["failed_cases"] == 1
    assert agent_runtime_report.route["route_mode_counts"] == {"shadow": 1, "takeover": 1, "primary": 1}
    assert agent_runtime_report.safety["safety_pass_rate"] == 0.6667
    assert agent_runtime_report.memory["memory_write_cases"] == 1
    assert agent_runtime_report.fallback["failed_case_refs"] == ["router_low_risk:C3"]
    assert "## Route" in markdown
    assert "## Safety" in markdown
    assert "## Memory" in markdown
    assert "## Fallback" in markdown
