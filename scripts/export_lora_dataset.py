from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, Field, ValidationError

from backend.app.lora.dataset import ALLOWED_EXAMPLE_FIELDS, FORBIDDEN_FIELD_NAMES, LoraTrainingExample
from backend.app.lora.dataset_quality import build_lora_dataset_quality_report, split_lora_dataset


class LoraDatasetExportReport(BaseModel):
    total_records: int
    exported_records: int
    skipped_records: int
    output_path: str
    warnings: list[str] = Field(default_factory=list)
    quality_report_path: str | None = None


def export_lora_dataset(
    records: Iterable[Mapping[str, Any]],
    output_path: str | Path,
    *,
    max_text_chars: int = 500,
    report_path: str | Path | None = None,
    split_ratios: dict[str, float] | None = None,
) -> LoraDatasetExportReport:
    output = Path(output_path)
    examples: list[LoraTrainingExample] = []
    warnings: list[str] = []
    total = 0
    for total, record in enumerate(records, start=1):
        payload = _sanitize_record(record, index=total, max_text_chars=max_text_chars, warnings=warnings)
        try:
            example = LoraTrainingExample.model_validate(payload)
        except ValidationError as exc:
            warnings.append(f"record {total} skipped: {exc.errors()[0]['msg']}")
            continue
        examples.append(example)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([example.model_dump() for example in examples], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    resolved_report_path = Path(report_path) if report_path is not None else output.with_name("lora_dataset_report.json")
    splits = split_lora_dataset(examples, split_ratios or {"train": 0.8, "validation": 0.1, "test": 0.1})
    quality_report = build_lora_dataset_quality_report(examples, max_text_chars=max_text_chars, splits=splits)
    resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_report_path.write_text(
        json.dumps(quality_report.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return LoraDatasetExportReport(
        total_records=total,
        exported_records=len(examples),
        skipped_records=total - len(examples),
        output_path=str(output),
        warnings=warnings,
        quality_report_path=str(resolved_report_path),
    )


def _sanitize_record(
    record: Mapping[str, Any],
    *,
    index: int,
    max_text_chars: int,
    warnings: list[str],
) -> dict[str, Any]:
    payload = {key: value for key, value in record.items() if key in ALLOWED_EXAMPLE_FIELDS}
    dropped = sorted(key for key in record if key not in ALLOWED_EXAMPLE_FIELDS)
    if dropped:
        warnings.append(f"record {index} dropped fields: {', '.join(dropped)}")

    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        safe_metadata = {
            str(key): str(value)
            for key, value in metadata.items()
            if str(key).strip().lower() not in FORBIDDEN_FIELD_NAMES
        }
        dropped_metadata = sorted(set(str(key) for key in metadata) - set(safe_metadata))
        if dropped_metadata:
            warnings.append(f"record {index} dropped metadata fields: {', '.join(dropped_metadata)}")
        payload["metadata"] = safe_metadata

    for field in ("instruction", "input_text", "output_text"):
        if field in payload and isinstance(payload[field], str) and len(payload[field]) > max_text_chars:
            payload[field] = payload[field][:max_text_chars]
            warnings.append(f"record {index} truncated {field}")
    return payload


def _load_records(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("LoRA source dataset must be a JSON list")
    return [dict(item) for item in payload]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a sanitized LoRA dataset dry-run JSON file.")
    parser.add_argument("--input", required=True, help="source JSON list")
    parser.add_argument("--output", required=True, help="sanitized output JSON file")
    parser.add_argument("--report-output", default=None, help="quality report JSON path")
    parser.add_argument("--max-text-chars", type=int, default=500)
    parser.add_argument("--json", action="store_true", help="print export report JSON")
    args = parser.parse_args(argv)

    report = export_lora_dataset(
        _load_records(args.input),
        args.output,
        max_text_chars=args.max_text_chars,
        report_path=args.report_output,
    )
    if args.json:
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    return 0 if report.skipped_records == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
