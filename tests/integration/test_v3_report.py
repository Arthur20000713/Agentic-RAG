from __future__ import annotations

from backend.app.evaluation.v3_report import build_v3_report
from backend.app.evaluation.v3_runner import V3CaseResult, V3EvaluationReport


def test_build_v3_report_summarizes_route_safety_memory_and_fallback() -> None:
    report = V3EvaluationReport(
        scenarios=["router_shadow", "router_low_risk"],
        metrics={},
        cases=[
            V3CaseResult(
                case_id="C1",
                category="general_qa",
                scenario="router_shadow",
                passed=True,
                checks={"intent": True, "safety": True},
                intent="general_qa",
                route_mode="shadow",
                selected_model="primary",
            ),
            V3CaseResult(
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
            V3CaseResult(
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

    v3_report = build_v3_report(report)
    markdown = v3_report.to_markdown()

    assert v3_report.summary["total_cases"] == 3
    assert v3_report.summary["failed_cases"] == 1
    assert v3_report.route["route_mode_counts"] == {"shadow": 1, "takeover": 1, "primary": 1}
    assert v3_report.safety["safety_pass_rate"] == 0.6667
    assert v3_report.memory["memory_write_cases"] == 1
    assert v3_report.fallback["failed_case_refs"] == ["router_low_risk:C3"]
    assert "## Route" in markdown
    assert "## Safety" in markdown
    assert "## Memory" in markdown
    assert "## Fallback" in markdown
