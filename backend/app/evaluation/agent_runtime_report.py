from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel


class AgentRuntimeReport(BaseModel):
    summary: dict[str, Any]
    route: dict[str, Any]
    safety: dict[str, Any]
    memory: dict[str, Any]
    fallback: dict[str, Any]
    performance: dict[str, Any]
    quality_gate: dict[str, Any]

    def to_markdown(self) -> str:
        lines = [
            "# Agent Runtime Report",
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
                "",
                "## Performance",
                "",
                f"- End-to-end latency P50: {self.performance['end_to_end_latency_ms']['p50']:.3f} ms",
                f"- End-to-end latency P95: {self.performance['end_to_end_latency_ms']['p95']:.3f} ms",
                f"- Model latency P50: {self.performance['model_latency_ms']['p50']:.3f} ms",
                f"- Model latency P95: {self.performance['model_latency_ms']['p95']:.3f} ms",
                f"- Tokens complete: {str(self.performance['tokens_complete']).lower()}",
                f"- Cost complete: {str(self.performance['cost_complete']).lower()}",
                "",
                "## Quality Gate",
                "",
                f"- Status: {self.quality_gate.get('status', 'not_evaluated')}",
            ]
        )
        for reason in self.quality_gate.get("reasons", []):
            lines.append(f"- Reason: {reason}")
        by_scenario = self.performance.get("by_scenario", {})
        if by_scenario:
            lines.extend(
                [
                    "",
                    "## Scenario Metrics",
                    "",
                    "| Scenario | Success | E2E P50/P95 ms | Model P50/P95 ms | Tokens | Cost USD | Fallback | Takeover | Escalation | Safety |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for scenario, item in by_scenario.items():
                e2e = item["end_to_end_latency_ms"]
                model = item["model_latency_ms"]
                tokens = item["total_tokens"] if item["tokens_complete"] else "unknown"
                cost = item["total_cost_usd"] if item["cost_complete"] else "unknown"
                lines.append(
                    f"| {scenario} | {item['task_success_rate']:.2%} | {e2e['p50']:.3f}/{e2e['p95']:.3f} | "
                    f"{model['p50']:.3f}/{model['p95']:.3f} | {tokens} | {cost} | {item['fallback_rate']:.2%} | "
                    f"{item['local_takeover_rate']:.2%} | {item['primary_escalation_rate']:.2%} | "
                    f"{item['safety_pass_rate']:.2%} |"
                )
        return "\n".join(lines) + "\n"


def build_agent_runtime_report(evaluation_report: Any) -> AgentRuntimeReport:
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
    end_to_end_latencies = [float(item.end_to_end_latency_ms) for item in cases]
    model_latencies = [float(item.model_latency_ms) for item in cases]
    tokens_complete = all(item.tokens_complete for item in cases)
    cost_complete = all(item.cost_complete for item in cases)
    known_input = sum(item.known_input_tokens for item in cases)
    known_output = sum(item.known_output_tokens for item in cases)
    known_total = sum(item.known_total_tokens for item in cases)
    known_cost = sum(item.known_total_cost_usd for item in cases)
    metrics = evaluation_report.metrics if isinstance(evaluation_report.metrics, dict) else {}

    return AgentRuntimeReport(
        summary={
            "mode": getattr(evaluation_report, "mode", "agent_runtime"),
            "scenarios": list(getattr(evaluation_report, "scenarios", [])),
            "evidence_kind": getattr(evaluation_report, "evidence_kind", "scripted"),
            "performance_claim_allowed": getattr(evaluation_report, "performance_claim_allowed", False),
            "benchmark_context": dict(getattr(evaluation_report, "benchmark_context", {})),
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
        performance={
            "end_to_end_latency_ms": _latency_summary(end_to_end_latencies),
            "model_latency_ms": _latency_summary(model_latencies),
            "known_input_tokens": known_input,
            "known_output_tokens": known_output,
            "known_total_tokens": known_total,
            "tokens_complete": tokens_complete,
            "input_tokens": known_input if tokens_complete else None,
            "output_tokens": known_output if tokens_complete else None,
            "total_tokens": known_total if tokens_complete else None,
            "known_total_cost_usd": known_cost,
            "cost_complete": cost_complete,
            "total_cost_usd": known_cost if cost_complete else None,
            "cost_scope": "api_token_only",
            "by_scenario": metrics.get("by_scenario", {}),
        },
        quality_gate=metrics.get("quality_gate", {}),
    )


def _case_refs(cases: Any) -> list[str]:
    return [f"{item.scenario}:{item.case_id}" for item in cases]


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {"p50": _percentile(values, 0.50), "p95": _percentile(values, 0.95)}


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 3)
