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
            safety_gate_status="passed",
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


def test_model_registry_entry_records_v5_training_metadata() -> None:
    path = _tmp_path()
    registry = ModelRegistry(path)

    registry.add_model(
        ModelRegistryEntry(
            model_id="lora-slot-v2",
            version="2026-05-19",
            adapter_path="C:/tmp/lora_adapters/slot_v2",
            task_type="slot_extraction",
            base_model="qwen2.5:7b-instruct",
            training_dataset_hash="sha256:abc123",
            eval_report_path="reports/lora/slot_v2_eval.json",
            safety_gate_status="passed",
            metrics={"lora_eval_pass_rate": 0.97},
        )
    )

    entry = ModelRegistry(path).get_model("lora-slot-v2")

    assert entry is not None
    assert entry.base_model == "qwen2.5:7b-instruct"
    assert entry.training_dataset_hash == "sha256:abc123"
    assert entry.eval_report_path == "reports/lora/slot_v2_eval.json"
    assert entry.safety_gate_status == "passed"


def test_model_registry_loads_legacy_entries_with_unknown_gate_status() -> None:
    path = _tmp_path()
    path.write_text(
        """
[
  {
    "model_id": "legacy",
    "version": "2026-05-14",
    "adapter_path": "models/legacy",
    "task_type": "slot_extraction",
    "enabled_for_inference": false,
    "metrics": {}
  }
]
""",
        encoding="utf-8",
    )

    entry = ModelRegistry(path).get_model("legacy")

    assert entry is not None
    assert entry.base_model is None
    assert entry.training_dataset_hash is None
    assert entry.eval_report_path is None
    assert entry.safety_gate_status == "unknown"


def test_model_registry_refuses_to_enable_adapter_without_passed_safety_gate() -> None:
    path = _tmp_path()
    registry = ModelRegistry(path)
    registry.add_model(
        ModelRegistryEntry(
            model_id="unsafe",
            version="2026-05-19",
            adapter_path="C:/tmp/lora_adapters/unsafe",
            task_type="slot_extraction",
            safety_gate_status="failed",
        )
    )

    with pytest.raises(ValueError, match="safety gate has not passed"):
        registry.enable_inference("unsafe", enabled=True)

    assert registry.get_model("unsafe").enabled_for_inference is False
