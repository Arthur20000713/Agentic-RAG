from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.failure_analysis import FAILURE_CATEGORIES, build_failure_report, categorize_failure
from backend.app.evaluation.golden_runner import EvaluationCaseResult
from backend.app.evaluation.metrics import compute_metrics


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


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
    assert metrics["failure_categories"]["NO_ANSWER_FALSE_POSITIVE"] == 1


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


def test_categorize_failure_distinguishes_v4_1_no_answer_and_citation_cases() -> None:
    assert categorize_failure(
        EvaluationCaseResult(
            case_id="no_answer_false_positive",
            category="no_answer",
            passed=False,
            checks={"no_answer": False},
            rag_result_observed=True,
            citation_count=1,
            source_uri_count=1,
            errors=[],
        )
    ) == "NO_ANSWER_FALSE_POSITIVE"
    assert categorize_failure(
        EvaluationCaseResult(
            case_id="low_confidence_accepted",
            category="general_qa",
            passed=False,
            checks={"citation": False},
            rag_result_observed=True,
            mapping_warnings=["RAG_LOW_CONFIDENCE_SCORE"],
            errors=["RAG_LOW_CONFIDENCE_SCORE"],
        )
    ) == "LOW_CONFIDENCE_ACCEPTED"
    assert categorize_failure(
        EvaluationCaseResult(
            case_id="missing_citation",
            category="general_qa",
            passed=False,
            checks={"citation": False},
            rag_result_observed=True,
            citation_count=0,
            source_uri_count=1,
            errors=[],
        )
    ) == "MISSING_CITATION"


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


def test_compute_metrics_outputs_v4_1_failure_category_counts() -> None:
    results = [
        EvaluationCaseResult(
            case_id="no_answer_false_positive",
            category="no_answer",
            passed=False,
            checks={"no_answer": False},
            rag_result_observed=True,
        ),
        EvaluationCaseResult(
            case_id="low_confidence_accepted",
            category="general_qa",
            passed=False,
            checks={"citation": False},
            rag_result_observed=True,
            errors=["RAG_LOW_CONFIDENCE_CITATION"],
            mapping_warnings=["RAG_LOW_CONFIDENCE_CITATION"],
        ),
        EvaluationCaseResult(
            case_id="missing_citation",
            category="general_qa",
            passed=False,
            checks={"citation": False},
            rag_result_observed=True,
            citation_count=0,
            source_uri_count=1,
        ),
    ]

    metrics = compute_metrics(results)

    assert metrics["failure_categories"]["NO_ANSWER_FALSE_POSITIVE"] == 1
    assert metrics["failure_categories"]["LOW_CONFIDENCE_ACCEPTED"] == 1
    assert metrics["failure_categories"]["MISSING_CITATION"] == 1


def test_compute_metrics_outputs_real_rag_observability_counts() -> None:
    results = [
        EvaluationCaseResult(
            case_id="with_sources",
            category="general_qa",
            passed=True,
            checks={"rag_call": True, "citation": True},
            rag_result_observed=True,
            citation_count=1,
            source_uri_count=2,
            mapping_warnings=["RAG_CITATION_SYNTHESIZED_FROM_HIT"],
        ),
        EvaluationCaseResult(
            case_id="timeout",
            category="general_qa",
            passed=False,
            checks={"rag_call": True, "citation": False},
            rag_result_observed=True,
            citation_count=0,
            source_uri_count=0,
            mapping_warnings=["RAG_MAPPING_PARTIAL_SOURCE_URI"],
            rag_error_code="RAG_TIMEOUT",
            errors=["RAG_TIMEOUT", "RAG_MAPPING_PARTIAL_SOURCE_URI"],
        ),
    ]

    metrics = compute_metrics(results)

    assert metrics["rag_citation_coverage"] == 0.5
    assert metrics["source_uri_coverage"] == 0.5
    assert metrics["mapping_warning_counts"]["RAG_CITATION_SYNTHESIZED_FROM_HIT"] == 1
    assert metrics["mapping_warning_counts"]["RAG_MAPPING_PARTIAL_SOURCE_URI"] == 1
    assert metrics["rag_error_counts"]["RAG_TIMEOUT"] == 1


def test_build_failure_report_outputs_categories_and_examples() -> None:
    results = [
        EvaluationCaseResult(
            case_id="case_bad_mapping",
            category="general_qa",
            passed=False,
            checks={"citation": False},
            tools_used=["livestock_rag_search"],
            errors=["RAG_MAPPING_PARTIAL_SOURCE_URI"],
        )
    ]

    class Report:
        metrics = compute_metrics(results)
        cases = results

    path = build_failure_report(Report(), _tmp_dir() / "failure_analysis.md")
    text = path.read_text(encoding="utf-8")

    assert "BAD_MAPPING" in text
    assert "case_bad_mapping" in text
