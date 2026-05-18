from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.evaluation.corpus_batch import load_corpus_batch, validate_corpus_batch


def _workspace_tmp() -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def _batch_path(root: Path, text: str) -> Path:
    path = root / "batch.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _yaml_path(path: Path) -> str:
    return path.as_posix()


def test_load_corpus_batch_reads_valid_yaml() -> None:
    root = _workspace_tmp()
    local_file = root / "calf_health.md"
    local_file.write_text("human curated summary", encoding="utf-8")
    local_file_value = _yaml_path(local_file)
    path = _batch_path(
        root,
        f"""
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
created_at: "2026-05-18"
status: planned
sources:
  - source_id: umn_preweaning_calf_health
    ingestion_mode: summary_only
    local_file: "{local_file_value}"
    expected_topics: [calf_health, diarrhea]
quality_gate:
  min_pass_rate: 0.90
  min_no_answer_accuracy: 0.95
  min_source_uri_coverage: 0.95
  required_safety_pass_rate: 1.0
""",
    )

    batch = load_corpus_batch(path)

    assert batch.batch_id == "batch_002"
    assert batch.collection == "livestock_v4_2"
    assert batch.sources[0].source_id == "umn_preweaning_calf_health"
    assert batch.quality_gate.min_no_answer_accuracy == 0.95
    assert validate_corpus_batch(batch) == []


def test_validate_corpus_batch_reports_missing_required_fields() -> None:
    root = _workspace_tmp()
    batch = load_corpus_batch(
        _batch_path(
            root,
            """
batch_id: ""
sources: []
""",
        )
    )

    failures = validate_corpus_batch(batch)

    assert "batch missing required field: batch_id" in failures
    assert "batch missing required field: collection" in failures
    assert "batch missing required field: manifest" in failures
    assert "batch missing required field: sources" in failures


def test_validate_corpus_batch_requires_unique_source_id() -> None:
    root = _workspace_tmp()
    first_file = root / "first.md"
    second_file = root / "second.md"
    first_file.write_text("first", encoding="utf-8")
    second_file.write_text("second", encoding="utf-8")
    first_file_value = _yaml_path(first_file)
    second_file_value = _yaml_path(second_file)
    batch = load_corpus_batch(
        _batch_path(
            root,
            f"""
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
sources:
  - source_id: duplicate_source
    ingestion_mode: summary_only
    local_file: "{first_file_value}"
  - source_id: duplicate_source
    ingestion_mode: metadata_only
    local_file: "{second_file_value}"
""",
        )
    )

    assert "duplicate source_id in batch: duplicate_source" in validate_corpus_batch(batch)


def test_validate_corpus_batch_rejects_unknown_ingestion_mode() -> None:
    root = _workspace_tmp()
    local_file = root / "source.md"
    local_file.write_text("source", encoding="utf-8")
    local_file_value = _yaml_path(local_file)
    batch = load_corpus_batch(
        _batch_path(
            root,
            f"""
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
sources:
  - source_id: bad_mode
    ingestion_mode: scrape_full_text
    local_file: "{local_file_value}"
""",
        )
    )

    assert "source bad_mode has unsupported ingestion_mode: scrape_full_text" in validate_corpus_batch(batch)


def test_validate_corpus_batch_reports_missing_local_file() -> None:
    root = _workspace_tmp()
    missing_file = root / "missing.md"
    missing_file_value = _yaml_path(missing_file)
    batch = load_corpus_batch(
        _batch_path(
            root,
            f"""
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
sources:
  - source_id: missing_file_source
    ingestion_mode: summary_only
    local_file: "{missing_file_value}"
""",
        )
    )

    assert (
        f"source missing_file_source local_file does not exist: {missing_file_value}"
        in validate_corpus_batch(batch)
    )


def test_load_corpus_batch_rejects_non_mapping_yaml() -> None:
    root = _workspace_tmp()
    path = _batch_path(root, "- just\n- a\n- list\n")

    with pytest.raises(ValueError, match="corpus batch must be a YAML mapping"):
        load_corpus_batch(path)
