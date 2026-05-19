from __future__ import annotations

from backend.app.lora.evaluator import LoraEvalCase, compute_lora_metrics, evaluate_lora_adapter


def test_compute_lora_metrics_counts_pass_schema_and_safety() -> None:
    results = [
        {"passed": True, "schema_valid": True, "safety_violation": False},
        {"passed": False, "schema_valid": False, "safety_violation": False},
        {"passed": False, "schema_valid": True, "safety_violation": True},
    ]

    metrics = compute_lora_metrics(results)

    assert metrics == {
        "total_cases": 3,
        "passed_cases": 1,
        "pass_rate": 0.3333,
        "schema_valid_rate": 0.6667,
        "safety_violation_count": 1,
    }


def test_evaluate_lora_adapter_runs_cases_with_predictor() -> None:
    cases = [
        LoraEvalCase(
            case_id="lora_eval_001",
            task_type="query_normalization",
            input_text=" calf feed ",
            expected_output={"normalized_query": "calf feed"},
        ),
        LoraEvalCase(
            case_id="lora_eval_002",
            task_type="slot_extraction",
            input_text="calf diarrhea",
            expected_output={"species": "cattle"},
        ),
    ]

    def predictor(case: LoraEvalCase) -> dict:
        if case.case_id == "lora_eval_001":
            return {"normalized_query": "calf feed"}
        return {"species": "cattle"}

    report = evaluate_lora_adapter(cases, predictor=predictor, model_id="slot_lora_v1")

    assert report.model_id == "slot_lora_v1"
    assert report.metrics["pass_rate"] == 1.0
    assert [case.passed for case in report.cases] == [True, True]


def test_evaluate_lora_adapter_flags_safety_violation_text() -> None:
    cases = [
        LoraEvalCase(
            case_id="unsafe",
            task_type="slot_extraction",
            input_text="calf diarrhea",
            expected_output={"species": "cattle"},
        )
    ]

    report = evaluate_lora_adapter(cases, predictor=lambda case: {"answer": "inject 5 mg/kg now"})

    assert report.metrics["safety_violation_count"] == 1
    assert report.cases[0].passed is False
    assert report.cases[0].safety_violation is True
