from __future__ import annotations

from backend.app.evaluation.failure_analysis import FAILURE_CATEGORIES, categorize_failure
from backend.app.evaluation.golden_runner import EvaluationCaseResult
from backend.app.evaluation.metrics import compute_metrics


def test_compute_metrics_counts_overall_and_named_checks() -> None:
    results = [
        EvaluationCaseResult(
            case_id="case_1",
            category="general_qa",
            passed=True,
            checks={"intent": True, "rag_call": True, "citation": True},
            intent="general_qa",
        ),
        EvaluationCaseResult(
            case_id="case_2",
            category="no_answer",
            passed=False,
            checks={"intent": True, "rag_call": True, "no_answer": False},
            intent="general_qa",
        ),
    ]

    metrics = compute_metrics(results)

    assert metrics["total_cases"] == 2
    assert metrics["passed_cases"] == 1
    assert metrics["failed_cases"] == 1
    assert metrics["pass_rate"] == 0.5
    assert metrics["intent_accuracy"] == 1.0
    assert metrics["rag_call_accuracy"] == 1.0
    assert metrics["citation_coverage"] == 1.0
    assert metrics["no_answer_accuracy"] == 0.0
    assert metrics["by_category"]["general_qa"]["pass_rate"] == 1.0
    assert metrics["by_category"]["no_answer"]["pass_rate"] == 0.0
    assert set(metrics["failure_categories"]) == set(FAILURE_CATEGORIES)
    assert metrics["failure_categories"]["UNSUPPORTED_CLAIM"] == 1


def test_categorize_failure_uses_fixed_categories() -> None:
    assert categorize_failure(
        EvaluationCaseResult(
            case_id="timeout",
            category="general_qa",
            passed=False,
            checks={"rag_call": False},
            errors=["RAG_TIMEOUT"],
        )
    ) == "TOOL_TIMEOUT"
    assert categorize_failure(
        EvaluationCaseResult(
            case_id="unavailable",
            category="general_qa",
            passed=False,
            checks={"rag_call": False},
            errors=["RAG_SERVER_PATH_MISSING"],
        )
    ) == "RAG_SERVER_UNAVAILABLE"
    assert categorize_failure(
        EvaluationCaseResult(
            case_id="mapping",
            category="general_qa",
            passed=False,
            checks={"citation": False},
            tools_used=["livestock_rag_search"],
            errors=["RAG_MAPPING_PARTIAL_SOURCE_URI"],
        )
    ) == "BAD_MAPPING"
    assert categorize_failure(
        EvaluationCaseResult(
            case_id="safety",
            category="high_risk_refusal",
            passed=False,
            checks={"safety": False},
            errors=[],
        )
    ) == "SAFETY_VIOLATION"


def test_compute_metrics_outputs_failure_category_counts() -> None:
    results = [
        EvaluationCaseResult(
            case_id="no_collection",
            category="general_qa",
            passed=False,
            checks={"rag_call": False},
            errors=["NO_COLLECTION"],
        ),
        EvaluationCaseResult(
            case_id="no_result",
            category="general_qa",
            passed=False,
            checks={"rag_call": False},
            errors=[],
        ),
        EvaluationCaseResult(
            case_id="low_score",
            category="general_qa",
            passed=False,
            checks={"citation": False},
            tools_used=["livestock_rag_search"],
            errors=["LOW_RETRIEVAL_SCORE"],
        ),
    ]

    metrics = compute_metrics(results)

    assert metrics["failure_categories"]["NO_COLLECTION"] == 1
    assert metrics["failure_categories"]["NO_RETRIEVAL_RESULT"] == 1
    assert metrics["failure_categories"]["LOW_RETRIEVAL_SCORE"] == 1
    assert all(category in metrics["failure_categories"] for category in FAILURE_CATEGORIES)
