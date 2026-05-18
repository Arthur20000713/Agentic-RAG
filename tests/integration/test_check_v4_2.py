from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.check_v4_2 import (
    check_batch_files,
    check_batch_report,
    check_golden_distribution,
    check_golden_source_ids,
    check_manifest_alignment,
)


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


def test_check_batch_files_allows_planned_sources_with_missing_local_files() -> None:
    root = _tmp_root()
    batch_path = root / "docs" / "rag_corpus" / "batches" / "batch_002.yaml"
    _write(
        batch_path,
        """
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
status: planned
sources:
  - source_id: umn_preweaning_calf_health
    ingestion_mode: summary_only
    local_file: C:\\tmp\\livestock_corpus\\batch_002\\umn_preweaning_calf_health.md
    status: planned
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


def test_check_batch_report_requires_quality_report_file() -> None:
    root = _tmp_root()

    failures = check_batch_report("batch_002", root)

    assert failures == [f"missing batch quality report: {root / 'docs' / 'rag_corpus' / 'reports' / 'batch_002_quality.md'}"]


def test_check_batch_report_accepts_planned_report_template() -> None:
    root = _tmp_root()
    report_path = root / "docs" / "rag_corpus" / "reports" / "batch_002_quality.md"
    _write(
        report_path,
        """
# Batch 002 Quality Report

- batch id: batch_002
- collection: livestock_v4_2
- source count: 10
- ingestion status: planned
- preflight status: not_run
- eval summary: not_run
- failure categories: not_run
""",
    )

    assert check_batch_report("batch_002", root) == []


def test_check_golden_source_ids_reports_unknown_sources() -> None:
    root = _tmp_root()
    manifest_path = root / "manifest.yaml"
    _write(
        manifest_path,
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
    golden_path = root / "golden.json"
    _write(
        golden_path,
        """
[
  {
    "case_id": "BAD_001",
    "category": "general_qa",
    "query": "question",
    "source_ids": ["missing_source"],
    "expected_answer_type": "answerable",
    "expected": {"intent": "general_qa", "rag_call": true, "citation": true}
  },
  {
    "case_id": "BAD_002",
    "category": "no_answer",
    "query": "question",
    "source_ids": ["missing_no_answer_source"],
    "expected_answer_type": "no_answer",
    "expected": {"intent": "general_qa", "rag_call": true, "no_answer": true}
  }
]
""",
    )

    failures = check_golden_source_ids(golden_path, manifest_path)

    assert "BAD_001 source_id missing_source not found in manifest" in failures
    assert "BAD_002 source_id missing_no_answer_source not found in manifest" in failures


def test_check_golden_distribution_reports_counts_when_below_minimums() -> None:
    golden_dir = _tmp_root()
    _write(golden_dir / "answerable.json", "[]")
    _write(golden_dir / "no_answer.json", "[]")
    _write(golden_dir / "safety.json", "[]")
    _write(golden_dir / "bilingual.json", "[]")
    _write(golden_dir / "all.json", "[]")

    failures = check_golden_distribution(golden_dir)

    assert failures == [
        "V4.2 golden distribution below minimums: answerable=0/35, no_answer=0/20, safety=0/15, bilingual=0/10, all=0/80"
    ]


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
