from __future__ import annotations

from dataclasses import dataclass


CORE_METRICS = (
    "pass_rate",
    "no_answer_accuracy",
    "source_uri_coverage",
    "safety_pass_rate",
)


@dataclass(frozen=True)
class EvalMetricDelta:
    name: str
    before: float
    after: float
    delta: float


def compare_eval_reports(before: dict, after: dict) -> list[EvalMetricDelta]:
    before_metrics = before.get("metrics") or {}
    after_metrics = after.get("metrics") or {}
    deltas: list[EvalMetricDelta] = []

    for metric_name in CORE_METRICS:
        if metric_name in before_metrics or metric_name in after_metrics:
            deltas.append(_metric_delta(metric_name, before_metrics, after_metrics))

    deltas.extend(_new_count_deltas("failure_category", before_metrics, after_metrics, "failure_categories"))
    deltas.extend(_new_count_deltas("mapping_warning", before_metrics, after_metrics, "mapping_warning_counts"))
    return deltas


def render_metric_delta_markdown(deltas: list[EvalMetricDelta]) -> str:
    lines = [
        "# Eval Report Delta",
        "",
        "| Metric | Before | After | Delta |",
        "|---|---:|---:|---:|",
    ]
    for item in deltas:
        lines.append(f"| {item.name} | {item.before:.4f} | {item.after:.4f} | {item.delta:+.4f} |")
    return "\n".join(lines) + "\n"


def _metric_delta(name: str, before_metrics: dict, after_metrics: dict) -> EvalMetricDelta:
    before_value = float(before_metrics.get(name, 0.0))
    after_value = float(after_metrics.get(name, 0.0))
    return EvalMetricDelta(name=name, before=before_value, after=after_value, delta=round(after_value - before_value, 10))


def _new_count_deltas(prefix: str, before_metrics: dict, after_metrics: dict, key: str) -> list[EvalMetricDelta]:
    before_counts = before_metrics.get(key) or {}
    after_counts = after_metrics.get(key) or {}
    deltas: list[EvalMetricDelta] = []
    for name, after_value in sorted(after_counts.items()):
        before_value = before_counts.get(name, 0)
        if name not in before_counts or after_value > before_value:
            before_float = float(before_value)
            after_float = float(after_value)
            deltas.append(
                EvalMetricDelta(
                    name=f"{prefix}:{name}",
                    before=before_float,
                    after=after_float,
                    delta=round(after_float - before_float, 10),
                )
            )
    return deltas
