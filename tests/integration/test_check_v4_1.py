from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.check_v4_1 import check_real_golden_sets, check_required_files, check_source_manifest


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
