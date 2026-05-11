from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.golden_runner import GoldenSetRunner
from scripts.run_eval import main as run_eval_main


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_golden_set_runner_writes_reports() -> None:
    output_dir = _tmp_dir()
    runner = GoldenSetRunner(output_dir=output_dir)

    report = runner.run()
    runner.write_outputs(report)

    assert report.metrics["total_cases"] == 60
    assert report.metrics["failed_cases"] == 0
    assert report.metrics["intent_accuracy"] == 1.0
    assert (output_dir / "eval_result.json").exists()
    assert (output_dir / "eval_result.csv").exists()
    assert (output_dir / "eval_summary.md").exists()


def test_run_eval_script_outputs_expected_files() -> None:
    output_dir = _tmp_dir()

    exit_code = run_eval_main(["--output-dir", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "eval_result.json").exists()
    assert (output_dir / "eval_result.csv").exists()
    assert (output_dir / "eval_summary.md").read_text(encoding="utf-8").startswith("# Evaluation Summary")
