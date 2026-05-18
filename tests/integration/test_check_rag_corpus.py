from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.check_rag_corpus import (
    build_rag_server_ingest_commands,
    collect_manifest_sources,
    validate_local_corpus_files,
)


def _tmp_root() -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_manifest(root: Path) -> Path:
    path = root / "source_manifest.yaml"
    path.write_text(
        """
version: 1
collection: livestock_v4_1
sources:
  - source_id: approved_source
    title: Approved source
    source_uri: https://example.com/approved
    language: EN
    organization: Example
    topics: [calf_health]
    usage: [knowledge_base]
    ingestion_status: approved_summary_only
    license_note: Summary only.
  - source_id: reference_source
    title: Reference source
    source_uri: https://example.com/reference
    language: EN
    organization: Example
    topics: [safety]
    usage: [reference]
    ingestion_status: reference_only
    license_note: Reference only.
""",
        encoding="utf-8",
    )
    return path


def test_collect_manifest_sources_loads_valid_manifest() -> None:
    manifest_path = _write_manifest(_tmp_root())

    entries = collect_manifest_sources(manifest_path)

    assert [entry.source_id for entry in entries] == ["approved_source", "reference_source"]


def test_validate_local_corpus_files_reports_missing_approved_files() -> None:
    root = _tmp_root()
    entries = collect_manifest_sources(_write_manifest(root))

    failures = validate_local_corpus_files(entries, root / "corpus")

    assert failures == [f"missing local corpus file for approved_source: {root / 'corpus' / 'approved_source.md'}"]


def test_validate_local_corpus_files_ignores_reference_only_sources() -> None:
    root = _tmp_root()
    entries = [entry for entry in collect_manifest_sources(_write_manifest(root)) if entry.source_id == "reference_source"]

    assert validate_local_corpus_files(entries, root / "corpus") == []


def test_build_rag_server_ingest_commands_uses_collection_and_safe_paths() -> None:
    root = _tmp_root()
    entries = collect_manifest_sources(_write_manifest(root))

    commands = build_rag_server_ingest_commands(entries, "livestock_v4_1", corpus_root=root / "corpus")

    assert commands == [
        f'python scripts/ingest.py --path "{root / "corpus" / "approved_source.md"}" --collection "livestock_v4_1"'
    ]
    assert "API" not in commands[0].upper()


def test_check_rag_corpus_dry_run_cli_does_not_require_real_rag_or_write_reports() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_rag_corpus.py",
            "--manifest",
            "docs/rag_corpus/source_manifest.yaml",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "DRY-RUN" in completed.stdout
    assert "scripts/ingest.py" in completed.stdout
    assert "API_KEY" not in completed.stdout
    assert not Path("reports/real_v4_1").exists()
