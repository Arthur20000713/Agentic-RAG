from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.quality_gate import QualityGateResult
from scripts.check_v4_2 import render_quality_gate_summary, run_quality_gate


def _tmp_root() -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_batch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
sources:
  - source_id: approved_source
    ingestion_mode: summary_only
    local_file: C:\\tmp\\livestock_corpus\\batch_002\\approved_source.md
quality_gate:
  min_pass_rate: 0.90
  min_no_answer_accuracy: 0.95
  min_source_uri_coverage: 0.95
  required_safety_pass_rate: 1.0
""",
        encoding="utf-8",
    )


def test_render_quality_gate_summary_includes_failed_reasons() -> None:
    summary = render_quality_gate_summary(
        QualityGateResult(passed=False, reasons=["pass_rate 0.55 below threshold 0.90"]),
    )

    assert "Quality gate: failed" in summary
    assert "pass_rate 0.55 below threshold 0.90" in summary


def test_run_quality_gate_returns_nonzero_for_failed_report() -> None:
    root = _tmp_root()
    report_path = root / "eval_result.json"
    batch_path = root / "batch.yaml"
    _write_json(
        report_path,
        {
            "mode": "real",
            "metrics": {
                "pass_rate": 0.55,
                "no_answer_accuracy": 0.0,
                "source_uri_coverage": 1.0,
                "safety_pass_rate": 1.0,
            },
        },
    )
    _write_batch(batch_path)

    assert run_quality_gate(report_path, batch_path) == 1


def test_run_quality_gate_returns_zero_for_passing_report() -> None:
    root = _tmp_root()
    report_path = root / "eval_result.json"
    batch_path = root / "batch.yaml"
    _write_json(
        report_path,
        {
            "mode": "real",
            "metrics": {
                "pass_rate": 0.95,
                "no_answer_accuracy": 0.96,
                "source_uri_coverage": 0.98,
                "safety_pass_rate": 1.0,
            },
        },
    )
    _write_batch(batch_path)

    assert run_quality_gate(report_path, batch_path) == 0


def test_check_v4_2_gate_cli_fails_for_skipped_report() -> None:
    root = _tmp_root()
    report_path = root / "eval_result.json"
    _write_json(
        report_path,
        {
            "mode": "real",
            "status": "skipped",
            "error_code": "RAG_SERVER_PATH_MISSING",
            "reason": "RAG_SERVER_PATH is not configured",
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v4_2.py",
            "--stage",
            "gate",
            "--report",
            str(report_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "real eval skipped: RAG_SERVER_PATH_MISSING" in completed.stderr
