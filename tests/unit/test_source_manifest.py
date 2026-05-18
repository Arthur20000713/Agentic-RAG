from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.source_manifest import load_source_manifest, validate_source_manifest


def _manifest_path(text: str) -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    path = root / "source_manifest.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_source_manifest_reads_valid_yaml() -> None:
    path = _manifest_path(
        """
version: 1
collection: livestock_v4_1
sources:
  - source_id: umn_preweaning_calf_health
    title: Pre-weaning calf health
    source_uri: https://extension.umn.edu/dairy-youngstock/pre-weaning-calf-health
    language: EN
    organization: University of Minnesota Extension
    topics: [calf_health, diarrhea]
    usage: [knowledge_base, eval]
    ingestion_status: approved_summary_only
    license_note: Link and human summary only.
"""
    )

    manifest = load_source_manifest(path)

    assert manifest.version == 1
    assert manifest.collection == "livestock_v4_1"
    assert manifest.sources[0].source_id == "umn_preweaning_calf_health"
    assert validate_source_manifest(manifest) == []


def test_validate_source_manifest_reports_missing_required_fields() -> None:
    manifest = load_source_manifest(
        _manifest_path(
            """
version: 1
collection: livestock_v4_1
sources:
  - source_id: incomplete_source
    title: Missing important fields
"""
        )
    )

    failures = validate_source_manifest(manifest)

    assert "source incomplete_source missing required field: source_uri" in failures
    assert "source incomplete_source missing required field: usage" in failures
    assert "source incomplete_source missing required field: ingestion_status" in failures


def test_validate_source_manifest_requires_unique_source_id() -> None:
    manifest = load_source_manifest(
        _manifest_path(
            """
version: 1
collection: livestock_v4_1
sources:
  - source_id: duplicate_source
    title: First
    source_uri: https://example.com/first
    language: EN
    organization: Example
    topics: [calf_health]
    usage: [eval]
    ingestion_status: eval_only
    license_note: Link only.
  - source_id: duplicate_source
    title: Second
    source_uri: https://example.com/second
    language: ZH
    organization: Example
    topics: [biosecurity]
    usage: [knowledge_base]
    ingestion_status: approved_summary_only
    license_note: Summary only.
"""
        )
    )

    assert "duplicate source_id: duplicate_source" in validate_source_manifest(manifest)


def test_validate_source_manifest_rejects_non_http_uri() -> None:
    manifest = load_source_manifest(
        _manifest_path(
            """
version: 1
collection: livestock_v4_1
sources:
  - source_id: local_file
    title: Local file
    source_uri: file:///tmp/local.pdf
    language: EN
    organization: Example
    topics: [calf_health]
    usage: [eval]
    ingestion_status: eval_only
    license_note: Link only.
"""
        )
    )

    assert "source local_file source_uri must start with http:// or https://" in validate_source_manifest(manifest)


def test_validate_source_manifest_rejects_unknown_usage_and_ingestion_status() -> None:
    manifest = load_source_manifest(
        _manifest_path(
            """
version: 1
collection: livestock_v4_1
sources:
  - source_id: bad_enums
    title: Bad enums
    source_uri: https://example.com/bad
    language: EN
    organization: Example
    topics: [calf_health]
    usage: [training]
    ingestion_status: scrape_full_text
    license_note: Link only.
"""
        )
    )

    failures = validate_source_manifest(manifest)

    assert "source bad_enums has unsupported usage: training" in failures
    assert "source bad_enums has unsupported ingestion_status: scrape_full_text" in failures


def test_project_source_manifest_validates() -> None:
    manifest = load_source_manifest("docs/rag_corpus/source_manifest.yaml")

    assert manifest.collection == "livestock_v4_1"
    assert len(manifest.sources) >= 8
    assert validate_source_manifest(manifest) == []
