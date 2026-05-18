from __future__ import annotations

from pathlib import Path
from typing import Any, Literal


FailureCategory = Literal[
    "NO_COLLECTION",
    "NO_RETRIEVAL_RESULT",
    "LOW_RETRIEVAL_SCORE",
    "NO_ANSWER_FALSE_POSITIVE",
    "LOW_CONFIDENCE_ACCEPTED",
    "MISSING_CITATION",
    "BAD_MAPPING",
    "UNSUPPORTED_CLAIM",
    "SAFETY_VIOLATION",
    "TOOL_TIMEOUT",
    "RAG_SERVER_UNAVAILABLE",
]

FAILURE_CATEGORIES: tuple[FailureCategory, ...] = (
    "NO_COLLECTION",
    "NO_RETRIEVAL_RESULT",
    "LOW_RETRIEVAL_SCORE",
    "NO_ANSWER_FALSE_POSITIVE",
    "LOW_CONFIDENCE_ACCEPTED",
    "MISSING_CITATION",
    "BAD_MAPPING",
    "UNSUPPORTED_CLAIM",
    "SAFETY_VIOLATION",
    "TOOL_TIMEOUT",
    "RAG_SERVER_UNAVAILABLE",
)

TIMEOUT_ERRORS = {"TOOL_TIMEOUT", "RAG_TIMEOUT", "RAG_SERVER_TIMEOUT"}
RAG_UNAVAILABLE_ERRORS = {
    "RAG_SERVER_UNAVAILABLE",
    "RAG_SERVER_PATH_MISSING",
    "RAG_SERVER_PATH_NOT_FOUND",
    "RAG_MCP_ERROR",
    "RAG_INTERNAL_ERROR",
}
LOW_CONFIDENCE_ERRORS = {
    "RAG_LOW_CONFIDENCE_SCORE",
    "RAG_LOW_CONFIDENCE_CITATION",
}


def categorize_failure(result: Any) -> FailureCategory | None:
    if result.passed:
        return None

    errors = {str(error) for error in getattr(result, "errors", [])}
    checks = dict(getattr(result, "checks", {}) or {})

    if errors & TIMEOUT_ERRORS:
        return "TOOL_TIMEOUT"
    if errors & RAG_UNAVAILABLE_ERRORS:
        return "RAG_SERVER_UNAVAILABLE"
    if "NO_COLLECTION" in errors:
        return "NO_COLLECTION"
    if "LOW_RETRIEVAL_SCORE" in errors:
        return "LOW_RETRIEVAL_SCORE"
    if checks.get("no_answer") is False and getattr(result, "category", None) == "no_answer":
        return "NO_ANSWER_FALSE_POSITIVE"
    if errors & LOW_CONFIDENCE_ERRORS:
        return "LOW_CONFIDENCE_ACCEPTED"
    if "BAD_MAPPING" in errors or any(error.startswith("RAG_MAPPING_") for error in errors):
        return "BAD_MAPPING"
    if "UNSUPPORTED_CLAIM" in errors or "VERIFIER_UNSUPPORTED_CLAIM" in errors:
        return "UNSUPPORTED_CLAIM"
    if any("SAFETY" in error for error in errors) or checks.get("safety") is False:
        return "SAFETY_VIOLATION"
    if checks.get("rag_call") is False:
        return "NO_RETRIEVAL_RESULT"
    if checks.get("citation") is False:
        return "MISSING_CITATION"
    if checks.get("no_answer") is False:
        return "UNSUPPORTED_CLAIM"
    return "UNSUPPORTED_CLAIM"


def build_failure_summary(results: list[Any]) -> dict[FailureCategory, int]:
    summary: dict[FailureCategory, int] = {category: 0 for category in FAILURE_CATEGORIES}
    for result in results:
        category = categorize_failure(result)
        if category is not None:
            summary[category] += 1
    return summary


def build_failure_report(report: Any, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Real RAG Failure Analysis", ""]

    if isinstance(report, dict) and report.get("status") == "skipped":
        summary: dict[FailureCategory, int] = {category: 0 for category in FAILURE_CATEGORIES}
        summary["RAG_SERVER_UNAVAILABLE"] = 1
        lines.extend(
            [
                "- Status: skipped",
                f"- Mode: {report.get('mode', 'real')}",
                f"- Error code: {report.get('error_code', '')}",
                f"- Reason: {report.get('reason', '')}",
                "",
                "## Failure Categories",
                "",
                "| Category | Count |",
                "|---|---:|",
            ]
        )
        for category in FAILURE_CATEGORIES:
            lines.append(f"| {category} | {summary[category]} |")
        lines.extend(
            [
                "",
                "## Examples",
                "",
                f"- `real_rag_unavailable` (RAG_SERVER_UNAVAILABLE): {report.get('reason', '')}",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    metrics = dict(getattr(report, "metrics", {}) or {})
    cases = list(getattr(report, "cases", []) or [])
    lines.extend(
        [
            f"- Total cases: {metrics.get('total_cases', len(cases))}",
            f"- Failed cases: {metrics.get('failed_cases', sum(1 for item in cases if not item.passed))}",
            "",
            "## Failure Categories",
            "",
            "| Category | Count |",
            "|---|---:|",
        ]
    )
    summary = metrics.get("failure_categories") or build_failure_summary(cases)
    for category in FAILURE_CATEGORIES:
        lines.append(f"| {category} | {summary.get(category, 0)} |")

    lines.extend(["", "## Examples", ""])
    failed_cases = [item for item in cases if not item.passed][:10]
    if not failed_cases:
        lines.append("- No failed cases.")
    for item in failed_cases:
        category = categorize_failure(item) or "PASSED"
        lines.append(
            f"- `{item.case_id}` ({item.category}, {category}): "
            f"errors={','.join(item.errors) or 'none'}; checks={item.checks}"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
