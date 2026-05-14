from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.lora.registry import ModelRegistry, ModelRegistryEntry


def _tmp_path() -> Path:
    path = Path(".tmp_tests") / f"{uuid4().hex}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_model_registry_starts_empty_when_file_is_missing() -> None:
    registry = ModelRegistry(_tmp_path())

    assert registry.list_models() == []
    assert registry.active_inference_models() == []


def test_model_registry_writes_and_reads_json_entries_with_inference_disabled_by_default() -> None:
    path = _tmp_path()
    registry = ModelRegistry(path)

    registry.add_model(
        ModelRegistryEntry(
            model_id="lora-slot-v1",
            version="2026-05-14",
            adapter_path="models/lora-slot-v1",
            task_type="slot_extraction",
            metrics={"validation_pass_rate": 1.0},
        )
    )
    reloaded = ModelRegistry(path)
    entry = reloaded.get_model("lora-slot-v1")

    assert entry is not None
    assert entry.model_id == "lora-slot-v1"
    assert entry.enabled_for_inference is False
    assert reloaded.active_inference_models() == []


def test_model_registry_can_explicitly_enable_inference() -> None:
    path = _tmp_path()
    registry = ModelRegistry(path)
    registry.add_model(
        ModelRegistryEntry(
            model_id="lora-format-v1",
            version="2026-05-14",
            adapter_path="models/lora-format-v1",
            task_type="measurement_formatting",
        )
    )

    registry.enable_inference("lora-format-v1", enabled=True)

    active = registry.active_inference_models()
    assert [entry.model_id for entry in active] == ["lora-format-v1"]
    assert registry.get_model("lora-format-v1").enabled_for_inference is True


def test_model_registry_raises_for_unknown_model_toggle() -> None:
    registry = ModelRegistry(_tmp_path())

    with pytest.raises(KeyError):
        registry.enable_inference("missing", enabled=True)
