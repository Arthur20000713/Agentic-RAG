from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError


ALLOWED_INGESTION_MODES = {"summary_only", "full_text", "metadata_only"}
REQUIRED_BATCH_FIELDS = ("batch_id", "collection", "manifest", "sources")
REQUIRED_SOURCE_FIELDS = ("source_id", "ingestion_mode", "local_file")


class CorpusQualityGateConfig(BaseModel):
    min_pass_rate: float = 0.90
    min_no_answer_accuracy: float = 0.95
    min_source_uri_coverage: float = 0.95
    required_safety_pass_rate: float = 1.0


class CorpusBatchSource(BaseModel):
    source_id: str | None = None
    ingestion_mode: str | None = None
    local_file: str | None = None
    expected_topics: list[str] = Field(default_factory=list)
    status: str | None = None


class CorpusBatch(BaseModel):
    batch_id: str | None = None
    collection: str | None = None
    manifest: str | None = None
    created_at: str | None = None
    status: str | None = None
    sources: list[CorpusBatchSource] = Field(default_factory=list)
    quality_gate: CorpusQualityGateConfig = Field(default_factory=CorpusQualityGateConfig)


def load_corpus_batch(path: str | Path) -> CorpusBatch:
    batch_path = Path(path)
    with batch_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}
    if not isinstance(payload, dict):
        raise ValueError("corpus batch must be a YAML mapping")
    try:
        return CorpusBatch.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid corpus batch: {exc}") from exc


def validate_corpus_batch(batch: CorpusBatch) -> list[str]:
    failures: list[str] = []
    for field_name in REQUIRED_BATCH_FIELDS:
        if _is_missing(getattr(batch, field_name)):
            failures.append(f"batch missing required field: {field_name}")

    seen_source_ids: set[str] = set()
    for index, source in enumerate(batch.sources):
        source_label = source.source_id or f"#{index + 1}"
        for field_name in REQUIRED_SOURCE_FIELDS:
            if _is_missing(getattr(source, field_name)):
                failures.append(f"source {source_label} missing required field: {field_name}")

        if source.source_id:
            if source.source_id in seen_source_ids:
                failures.append(f"duplicate source_id in batch: {source.source_id}")
            seen_source_ids.add(source.source_id)

        if source.ingestion_mode and source.ingestion_mode not in ALLOWED_INGESTION_MODES:
            failures.append(f"source {source_label} has unsupported ingestion_mode: {source.ingestion_mode}")

        if source.local_file and not Path(source.local_file).exists():
            failures.append(f"source {source_label} local_file does not exist: {source.local_file}")

    return failures


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    return False
