from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.check_v4_2 import check_batch_files, check_manifest_alignment


def _tmp_root() -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_check_batch_files_reports_invalid_batch_with_path_and_field() -> None:
    root = _tmp_root()
    batch_path = root / "docs" / "rag_corpus" / "batches" / "batch_002.yaml"
    _write(
        batch_path,
        """
batch_id: batch_002
collection: ""
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
sources: []
""",
    )

    failures = check_batch_files(root)

    assert any(str(batch_path) in failure and "collection" in failure for failure in failures)
    assert any(str(batch_path) in failure and "sources" in failure for failure in failures)


def test_check_batch_files_accepts_valid_existing_local_files() -> None:
    root = _tmp_root()
    local_file = root / "corpus" / "source.md"
    _write(local_file, "summary")
    batch_path = root / "docs" / "rag_corpus" / "batches" / "batch_002.yaml"
    _write(
        batch_path,
        f"""
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
sources:
  - source_id: umn_preweaning_calf_health
    ingestion_mode: summary_only
    local_file: "{local_file.as_posix()}"
""",
    )

    assert check_batch_files(root) == []


def test_check_manifest_alignment_reports_collection_and_source_mismatch() -> None:
    root = _tmp_root()
    local_file = root / "corpus" / "source.md"
    _write(local_file, "summary")
    _write(
        root / "docs" / "rag_corpus" / "manifests" / "livestock_v4_2.yaml",
        """
version: 2
collection: livestock_v4_2
sources:
  - source_id: known_source
    title: Known source
    source_uri: https://example.com/known
    language: EN
    organization: Example
    topics: [calf_health]
    usage: [knowledge_base]
    ingestion_status: approved_summary_only
    license_note: Summary only.
""",
    )
    batch_path = root / "docs" / "rag_corpus" / "batches" / "batch_002.yaml"
    _write(
        batch_path,
        f"""
batch_id: batch_002
collection: wrong_collection
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
sources:
  - source_id: missing_source
    ingestion_mode: summary_only
    local_file: "{local_file.as_posix()}"
""",
    )

    failures = check_manifest_alignment(root)

    assert any("collection mismatch" in failure and str(batch_path) in failure for failure in failures)
    assert any("source_id missing_source not found in manifest" in failure for failure in failures)


def test_check_v4_2_batch_cli_passes_without_real_rag() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v4_2.py",
            "--stage",
            "batch",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V4.2 checks passed for stage batch" in completed.stdout
    assert "RAG_SERVER_PATH" not in completed.stderr


def test_check_v4_2_full_cli_does_not_start_real_rag_by_default() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v4_2.py",
            "--stage",
            "full",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V4.2 checks passed for stage full" in completed.stdout
    assert "real RAG" not in completed.stdout
