from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel


class V3Report(BaseModel):
    summary: dict[str, Any]
    route: dict[str, Any]
    safety: dict[str, Any]
    memory: dict[str, Any]
    fallback: dict[str, Any]

    def to_markdown(self) -> str:
        lines = [
            "# V3 Report",
            "",
            "## Summary",
            "",
            f"- Total cases: {self.summary['total_cases']}",
            f"- Passed cases: {self.summary['passed_cases']}",
            f"- Failed cases: {self.summary['failed_cases']}",
            f"- Pass rate: {self.summary['pass_rate']:.2%}",
            "",
            "## Route",
            "",
            "| Field | Value |",
            "|---|---:|",
        ]
        for key, value in self.route["route_mode_counts"].items():
            lines.append(f"| route_mode:{key} | {value} |")
        for key, value in self.route["selected_model_counts"].items():
            lines.append(f"| selected_model:{key} | {value} |")

        lines.extend(
            [
                "",
                "## Safety",
                "",
                f"- Safety pass rate: {self.safety['safety_pass_rate']:.2%}",
                f"- Safety failures: {self.safety['safety_failures']}",
                "",
                "## Memory",
                "",
                f"- Memory write cases: {self.memory['memory_write_cases']}",
                f"- Memory write rate: {self.memory['memory_write_rate']:.2%}",
                "",
                "## Fallback",
                "",
                f"- Failed cases: {self.fallback['failed_cases']}",
                f"- Primary route cases: {self.fallback['primary_route_cases']}",
            ]
        )
        return "\n".join(lines) + "\n"


def build_v3_report(evaluation_report: Any) -> V3Report:
    cases = list(evaluation_report.cases)
    total = len(cases)
    passed = sum(1 for item in cases if item.passed)
    safety_applicable = [item for item in cases if "safety" in item.checks]
    safety_passed = sum(1 for item in safety_applicable if item.checks["safety"])
    memory_cases = [item for item in cases if "long_term_memory" in item.tools_used]
    failed_cases = [item for item in cases if not item.passed]
    primary_route_cases = [
        item
        for item in cases
        if item.route_mode == "primary" or (item.route_mode is None and item.selected_model == "primary")
    ]

    return V3Report(
        summary={
            "mode": getattr(evaluation_report, "mode", "v3"),
            "scenarios": list(getattr(evaluation_report, "scenarios", [])),
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": total - passed,
            "pass_rate": _rate(passed, total),
        },
        route={
            "route_mode_counts": dict(Counter(item.route_mode or "none" for item in cases)),
            "selected_model_counts": dict(Counter(item.selected_model or "none" for item in cases)),
            "takeover_cases": _case_refs(item for item in cases if item.route_mode == "takeover"),
            "shadow_cases": _case_refs(item for item in cases if item.route_mode == "shadow"),
        },
        safety={
            "safety_pass_rate": _rate(safety_passed, len(safety_applicable)),
            "safety_failures": len(safety_applicable) - safety_passed,
            "failed_cases": _case_refs(item for item in safety_applicable if not item.checks["safety"]),
        },
        memory={
            "memory_write_cases": len(memory_cases),
            "memory_write_rate": _rate(len(memory_cases), total),
            "cases": _case_refs(memory_cases),
        },
        fallback={
            "failed_cases": len(failed_cases),
            "failed_case_refs": _case_refs(failed_cases),
            "primary_route_cases": len(primary_route_cases),
            "primary_route_refs": _case_refs(primary_route_cases),
        },
    )


def _case_refs(cases: Any) -> list[str]:
    return [f"{item.scenario}:{item.case_id}" for item in cases]


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)
