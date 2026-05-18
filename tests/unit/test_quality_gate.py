from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.quality_gate import (
    QualityGateThresholds,
    evaluate_quality_gate,
    load_eval_report,
)


def _tmp_path() -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_load_eval_report_reads_json() -> None:
    path = _tmp_path() / "eval_result.json"
    path.write_text(json.dumps({"mode": "real", "metrics": {"pass_rate": 1.0}}), encoding="utf-8")

    assert load_eval_report(path)["mode"] == "real"


def test_evaluate_quality_gate_passes_when_metrics_meet_thresholds() -> None:
    report = {
        "mode": "real",
        "metrics": {
            "pass_rate": 0.95,
            "no_answer_accuracy": 0.96,
            "source_uri_coverage": 0.98,
            "safety_pass_rate": 1.0,
        },
    }

    result = evaluate_quality_gate(report, QualityGateThresholds())

    assert result.passed is True
    assert result.reasons == []


def test_evaluate_quality_gate_fails_with_threshold_reasons() -> None:
    report = {
        "mode": "real",
        "metrics": {
            "pass_rate": 0.55,
            "no_answer_accuracy": 0.0,
            "source_uri_coverage": 0.90,
            "safety_pass_rate": 0.99,
        },
    }

    result = evaluate_quality_gate(report, QualityGateThresholds())

    assert result.passed is False
    assert "pass_rate 0.55 below threshold 0.90" in result.reasons
    assert "no_answer_accuracy 0.00 below threshold 0.95" in result.reasons
    assert "source_uri_coverage 0.90 below threshold 0.95" in result.reasons
    assert "safety_pass_rate 0.99 below required 1.00" in result.reasons


def test_evaluate_quality_gate_rejects_skipped_real_eval() -> None:
    report = {
        "mode": "real",
        "status": "skipped",
        "error_code": "RAG_SERVER_PATH_MISSING",
        "reason": "RAG_SERVER_PATH is not configured",
    }

    result = evaluate_quality_gate(report, QualityGateThresholds())

    assert result.passed is False
    assert result.reasons == ["real eval skipped: RAG_SERVER_PATH_MISSING - RAG_SERVER_PATH is not configured"]
