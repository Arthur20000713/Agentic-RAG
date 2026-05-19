from __future__ import annotations

from backend.app.evaluation.model_quality_gate import ModelQualityThresholds, evaluate_model_quality_gate


def test_model_quality_gate_passes_when_metrics_meet_thresholds() -> None:
    report = {
        "status": "passed",
        "metrics": {
            "local_model_schema_valid_rate": 0.99,
            "local_model_timeout_rate": 0.01,
            "router_fallback_success_rate": 1.0,
            "low_risk_takeover_pass_rate": 0.96,
            "safety_redteam_pass_rate": 1.0,
            "lora_eval_pass_rate": 0.96,
            "regression_pass_rate": 1.0,
        },
    }

    result = evaluate_model_quality_gate(report, ModelQualityThresholds())

    assert result.passed is True
    assert result.reasons == []


def test_model_quality_gate_fails_for_skipped_report() -> None:
    result = evaluate_model_quality_gate({"status": "skipped", "reason": "local model missing"}, ModelQualityThresholds())

    assert result.passed is False
    assert result.reasons == ["V5 report skipped: local model missing"]


def test_model_quality_gate_reports_each_failed_metric() -> None:
    report = {
        "status": "passed",
        "metrics": {
            "local_model_schema_valid_rate": 0.90,
            "local_model_timeout_rate": 0.10,
            "router_fallback_success_rate": 0.5,
            "low_risk_takeover_pass_rate": 0.8,
            "safety_redteam_pass_rate": 0.9,
            "lora_eval_pass_rate": 0.7,
            "regression_pass_rate": 0.99,
        },
    }

    result = evaluate_model_quality_gate(report, ModelQualityThresholds())

    assert result.passed is False
    assert "local_model_schema_valid_rate 0.9 < 0.98" in result.reasons
    assert "local_model_timeout_rate 0.1 > 0.02" in result.reasons
    assert "router_fallback_success_rate 0.5 < 1.0" in result.reasons
    assert "low_risk_takeover_pass_rate 0.8 < 0.95" in result.reasons
    assert "safety_redteam_pass_rate 0.9 < 1.0" in result.reasons
    assert "lora_eval_pass_rate 0.7 < 0.95" in result.reasons
    assert "regression_pass_rate 0.99 < 1.0" in result.reasons
