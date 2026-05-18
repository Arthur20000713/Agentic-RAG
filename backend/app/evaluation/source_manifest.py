from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError


ALLOWED_USAGE = {"knowledge_base", "eval", "redteam", "reference"}
ALLOWED_INGESTION_STATUS = {
    "approved_summary_only",
    "approved_full_text",
    "eval_only",
    "reference_only",
    "blocked",
}
REQUIRED_SOURCE_FIELDS = (
    "source_id",
    "title",
    "source_uri",
    "language",
    "organization",
    "topics",
    "usage",
    "ingestion_status",
    "license_note",
)


class SourceManifestEntry(BaseModel):
    source_id: str | None = None
    title: str | None = None
    source_uri: str | None = None
    language: str | None = None
    organization: str | None = None
    source_type: str | None = None
    topics: list[str] | None = None
    usage: list[str] | None = None
    ingestion_status: str | None = None
    license_note: str | None = None
    reviewed_by: str | None = None
    summary: str | None = None
    local_path: str | None = None


class SourceManifest(BaseModel):
    version: int | None = None
    collection: str | None = None
    sources: list[SourceManifestEntry] = Field(default_factory=list)


def load_source_manifest(path: str | Path) -> SourceManifest:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}
    if not isinstance(payload, dict):
        raise ValueError("source manifest must be a YAML mapping")
    try:
        return SourceManifest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid source manifest: {exc}") from exc


def validate_source_manifest(manifest: SourceManifest) -> list[str]:
    failures: list[str] = []
    if manifest.version is None:
        failures.append("manifest missing required field: version")
    if not manifest.collection:
        failures.append("manifest missing required field: collection")
    if not manifest.sources:
        failures.append("manifest missing required field: sources")

    seen_source_ids: set[str] = set()
    for index, source in enumerate(manifest.sources):
        source_label = _source_label(source, index)
        for field_name in REQUIRED_SOURCE_FIELDS:
            if _is_missing(getattr(source, field_name)):
                failures.append(f"source {source_label} missing required field: {field_name}")

        if source.source_id:
            if source.source_id in seen_source_ids:
                failures.append(f"duplicate source_id: {source.source_id}")
            seen_source_ids.add(source.source_id)

        if source.source_uri and not source.source_uri.startswith(("http://", "https://")):
            failures.append(f"source {source_label} source_uri must start with http:// or https://")

        for usage in source.usage or []:
            if usage not in ALLOWED_USAGE:
                failures.append(f"source {source_label} has unsupported usage: {usage}")

        if source.ingestion_status and source.ingestion_status not in ALLOWED_INGESTION_STATUS:
            failures.append(f"source {source_label} has unsupported ingestion_status: {source.ingestion_status}")

    return failures


def _source_label(source: SourceManifestEntry, index: int) -> str:
    return source.source_id or f"#{index + 1}"


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    return False
