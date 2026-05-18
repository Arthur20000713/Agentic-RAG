from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.lora.dataset import LoraTrainingExample
from backend.app.lora.dataset_quality import build_lora_dataset_quality_report, split_lora_dataset


def _valid_payload() -> dict:
    return {
        "example_id": "lora_001",
        "task_type": "slot_extraction",
        "instruction": "Extract livestock disease slots as JSON.",
        "input_text": "Calf diarrhea for two days.",
        "output_text": '{"species":"cattle","symptoms":["diarrhea"],"duration_days":2}',
        "source": "rule_generated",
        "safety_level": "S2",
        "metadata": {"intent": "disease_consultation"},
    }


def test_lora_training_example_accepts_required_fields() -> None:
    example = LoraTrainingExample.model_validate(_valid_payload())

    assert example.example_id == "lora_001"
    assert example.task_type == "slot_extraction"
    assert example.source == "rule_generated"
    assert example.metadata["intent"] == "disease_consultation"


def test_lora_training_example_requires_core_fields() -> None:
    payload = _valid_payload()
    payload.pop("output_text")

    with pytest.raises(ValidationError):
        LoraTrainingExample.model_validate(payload)


def test_lora_training_example_forbids_extra_fields() -> None:
    payload = _valid_payload()
    payload["raw_rag_text"] = "full retrieved document body"

    with pytest.raises(ValidationError) as exc_info:
        LoraTrainingExample.model_validate(payload)

    assert "Extra inputs are not permitted" in str(exc_info.value)


def test_lora_training_example_forbids_sensitive_metadata_fields() -> None:
    payload = _valid_payload()
    payload["metadata"] = {"api_key": "secret"}

    with pytest.raises(ValidationError) as exc_info:
        LoraTrainingExample.model_validate(payload)

    assert "forbidden LoRA training fields" in str(exc_info.value)


def test_lora_training_example_forbids_rag_context_markers_in_text() -> None:
    payload = _valid_payload()
    payload["input_text"] = "rag_context: copied full retrieved text"

    with pytest.raises(ValidationError) as exc_info:
        LoraTrainingExample.model_validate(payload)

    assert "forbidden LoRA training content marker" in str(exc_info.value)


def test_split_lora_dataset_creates_train_validation_test_partitions() -> None:
    examples = [
        LoraTrainingExample.model_validate({**_valid_payload(), "example_id": f"lora_{index:03d}"})
        for index in range(10)
    ]

    splits = split_lora_dataset(examples, {"train": 0.6, "validation": 0.2, "test": 0.2})

    assert {key: len(value) for key, value in splits.items()} == {"train": 6, "validation": 2, "test": 2}
    assert [item.example_id for item in splits["train"]][:2] == ["lora_000", "lora_001"]
    assert [item.example_id for item in splits["test"]] == ["lora_008", "lora_009"]


def test_lora_dataset_quality_report_flags_duplicates_and_long_text() -> None:
    examples = [
        LoraTrainingExample.model_validate({**_valid_payload(), "example_id": "dup_001", "task_type": "slot_extraction"}),
        LoraTrainingExample.model_validate(
            {
                **_valid_payload(),
                "example_id": "dup_001",
                "task_type": "query_normalization",
                "input_text": "x" * 120,
            }
        ),
        LoraTrainingExample.model_validate(
            {**_valid_payload(), "example_id": "measure_001", "task_type": "measurement_formatting"}
        ),
    ]

    report = build_lora_dataset_quality_report(examples, max_text_chars=80)

    assert report.total_examples == 3
    assert report.duplicate_example_ids == ["dup_001"]
    assert report.overlong_example_ids == ["dup_001"]
    assert report.task_distribution == {
        "slot_extraction": 1,
        "query_normalization": 1,
        "measurement_formatting": 1,
    }
    assert report.ready_for_training is False
