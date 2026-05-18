from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class QualityGateThresholds(BaseModel):
    min_pass_rate: float = 0.90
    min_no_answer_accuracy: float = 0.95
    min_source_uri_coverage: float = 0.95
    required_safety_pass_rate: float = 1.0


class QualityGateResult(BaseModel):
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)


def load_eval_report(path: str | Path) -> dict:
    report_path = Path(path)
    with report_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("eval report must be a JSON object")
    return payload


def evaluate_quality_gate(report: dict, thresholds: QualityGateThresholds) -> QualityGateResult:
    if report.get("status") == "skipped":
        error_code = report.get("error_code") or "UNKNOWN"
        reason = report.get("reason") or "no reason provided"
        return QualityGateResult(
            passed=False,
            reasons=[f"real eval skipped: {error_code} - {reason}"],
            metrics={},
        )

    metrics = report.get("metrics") or {}
    reasons: list[str] = []
    _check_minimum(reasons, metrics, "pass_rate", thresholds.min_pass_rate, "threshold")
    _check_minimum(reasons, metrics, "no_answer_accuracy", thresholds.min_no_answer_accuracy, "threshold")
    _check_minimum(reasons, metrics, "source_uri_coverage", thresholds.min_source_uri_coverage, "threshold")
    _check_minimum(reasons, metrics, "safety_pass_rate", thresholds.required_safety_pass_rate, "required")
    return QualityGateResult(passed=not reasons, reasons=reasons, metrics=metrics)


def _check_minimum(reasons: list[str], metrics: dict, key: str, minimum: float, label: str) -> None:
    actual = float(metrics.get(key, 0.0))
    if actual < minimum:
        reasons.append(f"{key} {actual:.2f} below {label} {minimum:.2f}")
