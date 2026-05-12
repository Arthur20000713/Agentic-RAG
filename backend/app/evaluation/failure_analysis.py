from __future__ import annotations

from typing import Any, Literal


FailureCategory = Literal[
    "NO_COLLECTION",
    "NO_RETRIEVAL_RESULT",
    "LOW_RETRIEVAL_SCORE",
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
    if "BAD_MAPPING" in errors or any(error.startswith("RAG_MAPPING_") for error in errors):
        return "BAD_MAPPING"
    if "UNSUPPORTED_CLAIM" in errors or "VERIFIER_UNSUPPORTED_CLAIM" in errors:
        return "UNSUPPORTED_CLAIM"
    if any("SAFETY" in error for error in errors) or checks.get("safety") is False:
        return "SAFETY_VIOLATION"
    if checks.get("rag_call") is False:
        return "NO_RETRIEVAL_RESULT"
    if checks.get("citation") is False or checks.get("no_answer") is False:
        return "UNSUPPORTED_CLAIM"
    return "UNSUPPORTED_CLAIM"


def build_failure_summary(results: list[Any]) -> dict[FailureCategory, int]:
    summary: dict[FailureCategory, int] = {category: 0 for category in FAILURE_CATEGORIES}
    for result in results:
        category = categorize_failure(result)
        if category is not None:
            summary[category] += 1
    return summary
