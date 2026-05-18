from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.lora.dataset import LoraTrainingExample


SplitName = Literal["train", "validation", "test"]


class LoraDatasetQualityReport(BaseModel):
    total_examples: int
    duplicate_example_ids: list[str] = Field(default_factory=list)
    overlong_example_ids: list[str] = Field(default_factory=list)
    task_distribution: dict[str, int] = Field(default_factory=dict)
    split_distribution: dict[str, int] = Field(default_factory=dict)
    ready_for_training: bool = False


def split_lora_dataset(
    examples: list[LoraTrainingExample],
    ratios: dict[str, float],
) -> dict[SplitName, list[LoraTrainingExample]]:
    _validate_ratios(ratios)
    total = len(examples)
    train_count = int(total * ratios["train"])
    validation_count = int(total * ratios["validation"])
    test_count = total - train_count - validation_count
    return {
        "train": examples[:train_count],
        "validation": examples[train_count : train_count + validation_count],
        "test": examples[train_count + validation_count : train_count + validation_count + test_count],
    }


def build_lora_dataset_quality_report(
    examples: list[LoraTrainingExample],
    *,
    max_text_chars: int = 500,
    splits: dict[str, list[LoraTrainingExample]] | None = None,
) -> LoraDatasetQualityReport:
    duplicate_ids = _duplicate_ids(examples)
    overlong_ids = _overlong_ids(examples, max_text_chars=max_text_chars)
    task_distribution = dict(Counter(example.task_type for example in examples))
    split_distribution = {name: len(items) for name, items in (splits or {}).items()}
    return LoraDatasetQualityReport(
        total_examples=len(examples),
        duplicate_example_ids=duplicate_ids,
        overlong_example_ids=overlong_ids,
        task_distribution=task_distribution,
        split_distribution=split_distribution,
        ready_for_training=bool(examples) and not duplicate_ids and not overlong_ids,
    )


def _validate_ratios(ratios: dict[str, float]) -> None:
    required = {"train", "validation", "test"}
    missing = required - set(ratios)
    if missing:
        raise ValueError(f"missing split ratios: {', '.join(sorted(missing))}")
    total = sum(float(ratios[name]) for name in required)
    if abs(total - 1.0) > 0.0001:
        raise ValueError("split ratios must sum to 1.0")
    if any(float(ratios[name]) < 0 for name in required):
        raise ValueError("split ratios must be non-negative")


def _duplicate_ids(examples: list[LoraTrainingExample]) -> list[str]:
    counts = Counter(example.example_id for example in examples)
    return sorted(example_id for example_id, count in counts.items() if count > 1)


def _overlong_ids(examples: list[LoraTrainingExample], *, max_text_chars: int) -> list[str]:
    ids: list[str] = []
    for example in examples:
        if any(
            len(value) > max_text_chars
            for value in (example.instruction, example.input_text, example.output_text)
        ):
            ids.append(example.example_id)
    return sorted(set(ids))
