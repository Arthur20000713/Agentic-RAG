from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.v3_safety_runner import V3SafetyEvalRunner


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_v3_safety_eval_runner_outputs_pass_rate_and_reports() -> None:
    output_dir = _tmp_dir()
    runner = V3SafetyEvalRunner(output_dir=output_dir)

    report = runner.run()
    runner.write_outputs(report)

    assert report.metrics["total_cases"] == 3
    assert report.metrics["failed_cases"] == 0
    assert report.metrics["safety_pass_rate"] == 1.0
    assert all(item.hard_blocked for item in report.cases)
    assert all(item.sanitized for item in report.cases)
    assert (output_dir / "v3_safety_result.json").exists()
    assert (output_dir / "v3_safety_summary.md").exists()

    payload = json.loads((output_dir / "v3_safety_result.json").read_text(encoding="utf-8"))
    assert payload["metrics"]["safety_pass_rate"] == 1.0
    assert "V3 Safety Evaluation Summary" in (output_dir / "v3_safety_summary.md").read_text(encoding="utf-8")
