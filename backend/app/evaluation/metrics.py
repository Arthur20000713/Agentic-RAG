from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from backend.app.evaluation.failure_analysis import build_failure_summary


CHECK_TO_METRIC = {
    "intent": "intent_accuracy",
    "rag_call": "rag_call_accuracy",
    "citation": "citation_coverage",
    "no_answer": "no_answer_accuracy",
    "safety": "safety_pass_rate",
    "follow_up": "follow_up_accuracy",
    "structure": "structure_completeness",
}


def compute_metrics(results: Iterable[Any]) -> dict[str, Any]:
    items = list(results)
    total = len(items)
    passed = sum(1 for item in items if item.passed)

    metrics: dict[str, Any] = {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "pass_rate": _rate(passed, total),
        "by_category": _category_summary(items),
        "failure_categories": build_failure_summary(items),
    }

    for check_name, metric_name in CHECK_TO_METRIC.items():
        applicable = [item for item in items if check_name in item.checks]
        metrics[metric_name] = _rate(sum(1 for item in applicable if item.checks[check_name]), len(applicable))
    metrics.update(_rag_observability_summary(items))

    return metrics


def _rag_observability_summary(items: list[Any]) -> dict[str, Any]:
    applicable = [
        item
        for item in items
        if getattr(item, "rag_result_observed", False)
        or getattr(item, "citation_count", 0)
        or getattr(item, "source_uri_count", 0)
        or getattr(item, "mapping_warnings", [])
        or getattr(item, "rag_error_code", None)
    ]
    warning_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    for item in items:
        warning_counts.update(str(warning) for warning in getattr(item, "mapping_warnings", []) or [])
        error_code = getattr(item, "rag_error_code", None)
        if error_code:
            error_counts[str(error_code)] += 1
    return {
        "rag_citation_coverage": _rate(
            sum(1 for item in applicable if getattr(item, "citation_count", 0) > 0),
            len(applicable),
        ),
        "source_uri_coverage": _rate(
            sum(1 for item in applicable if getattr(item, "source_uri_count", 0) > 0),
            len(applicable),
        ),
        "mapping_warning_counts": dict(sorted(warning_counts.items())),
        "rag_error_counts": dict(sorted(error_counts.items())),
    }


def _category_summary(items: list[Any]) -> dict[str, dict[str, int | float]]:
    counts = Counter(item.category for item in items)
    passed = Counter(item.category for item in items if item.passed)
    return {
        category: {
            "total": total,
            "passed": passed[category],
            "pass_rate": _rate(passed[category], total),
        }
        for category, total in sorted(counts.items())
    }


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)
