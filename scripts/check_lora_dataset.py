from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.lora.dataset import ALLOWED_EXAMPLE_FIELDS, FORBIDDEN_FIELD_NAMES, LoraTrainingExample


REQUIRED_SPLITS = ("train", "validation", "test")


def check_lora_dataset(path: str | Path) -> list[str]:
    dataset_path = Path(path)
    if not dataset_path.exists():
        return [f"dataset file not found: {dataset_path}"]

    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"dataset JSON invalid: {exc.msg}"]

    if not isinstance(payload, dict):
        return ["dataset must be an object with train/validation/test splits"]

    failures: list[str] = []
    for split in REQUIRED_SPLITS:
        items = payload.get(split)
        if not isinstance(items, list) or not items:
            failures.append(f"dataset missing non-empty split: {split}")
            continue
        failures.extend(_check_split(split, items))
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate sanitized LoRA training dataset splits.")
    parser.add_argument("--input", required=True, help="dataset JSON with train/validation/test splits")
    parser.add_argument("--optional", action="store_true", help="return 0 when input dataset is missing")
    args = parser.parse_args(argv)

    failures = check_lora_dataset(args.input)
    missing_only = len(failures) == 1 and failures[0].startswith("dataset file not found:")
    if failures:
        if args.optional and missing_only:
            print(f"SKIPPED: {failures[0]}")
            return 0
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("LoRA dataset checks passed")
    return 0


def _check_split(split: str, items: list[Any]) -> list[str]:
    failures: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            failures.append(f"{split}[{index}]: example must be an object")
            continue
        failures.extend(_forbidden_field_failures(split, index, item))
        allowed_payload = {key: value for key, value in item.items() if key in ALLOWED_EXAMPLE_FIELDS}
        try:
            LoraTrainingExample.model_validate(allowed_payload)
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(part) for part in first.get("loc", ())) or "payload"
            failures.append(f"{split}[{index}]: invalid field {location}: {first.get('msg')}")
    return failures


def _forbidden_field_failures(split: str, index: int, item: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    forbidden_top_level = sorted(set(_normalized_keys(item)) & FORBIDDEN_FIELD_NAMES)
    if forbidden_top_level:
        failures.append(f"{split}[{index}]: forbidden fields: {', '.join(forbidden_top_level)}")

    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        forbidden_metadata = sorted(set(_normalized_keys(metadata)) & FORBIDDEN_FIELD_NAMES)
        if forbidden_metadata:
            failures.append(f"{split}[{index}]: forbidden metadata fields: {', '.join(forbidden_metadata)}")
    return failures


def _normalized_keys(mapping: dict[str, Any]) -> list[str]:
    return [str(key).strip().lower() for key in mapping]


if __name__ == "__main__":
    raise SystemExit(main())
