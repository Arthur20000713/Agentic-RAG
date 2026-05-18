from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.check_v4_1 import (
    check_real_golden_sets,
    check_real_rag_report,
    check_required_files,
    check_source_manifest,
    run_real_rag_smoke,
)


def _tmp_root() -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_check_required_files_reports_missing_baseline_files() -> None:
    tmp_root = _tmp_root()
    (tmp_root / "README.md").write_text("readme", encoding="utf-8")

    failures = check_required_files(tmp_root)

    assert "missing required file: DEV_SPEC_v4_1.md" in failures
    assert "missing required file: docs/V4_1_BASELINE.md" in failures


def test_check_source_manifest_requires_manifest_file() -> None:
    failures = check_source_manifest(_tmp_root())

    assert failures == ["missing required file: docs/rag_corpus/source_manifest.yaml"]


def test_check_real_golden_sets_requires_grouped_real_sets() -> None:
    tmp_root = _tmp_root()
    fixture_dir = tmp_root / "tests" / "fixtures" / "real_golden_v4_1"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "answerable.json").write_text("[]", encoding="utf-8")

    failures = check_real_golden_sets(tmp_root)

    assert "missing required file: tests/fixtures/real_golden_v4_1/no_answer.json" in failures
    assert "missing required file: tests/fixtures/real_golden_v4_1/safety.json" in failures


def test_check_v4_1_baseline_cli_passes_without_real_rag() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v4_1.py",
            "--stage",
            "baseline",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V4.1 checks passed for stage baseline" in completed.stdout
    assert "RAG_SERVER_PATH" not in completed.stderr


def test_check_v4_1_full_cli_does_not_start_real_rag_by_default() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v4_1.py",
            "--stage",
            "full",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V4.1 checks passed for stage full" in completed.stdout
    assert "real RAG smoke" not in completed.stdout


def test_check_real_rag_report_accepts_skipped_report_with_reason() -> None:
    output_dir = _tmp_root()
    (output_dir / "eval_result.json").write_text(
        """
{
  "status": "skipped",
  "mode": "real",
  "error_code": "RAG_SERVER_PATH_MISSING",
  "reason": "RAG_SERVER_PATH is not configured"
}
""",
        encoding="utf-8",
    )

    assert check_real_rag_report(output_dir) == []


def test_run_real_rag_smoke_optional_writes_skipped_report_when_path_missing(monkeypatch) -> None:
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    monkeypatch.delenv("RAG_SERVER_PYTHON", raising=False)
    output_dir = _tmp_root()

    exit_code = run_real_rag_smoke(optional=True, output_dir=output_dir)

    assert exit_code == 0
    failures = check_real_rag_report(output_dir)
    assert failures == []
    assert "RAG_SERVER_PATH_MISSING" in (output_dir / "eval_result.json").read_text(encoding="utf-8")
