from __future__ import annotations

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
