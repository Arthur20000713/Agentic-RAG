from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.lora.dataset import LoraTrainingExample


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
