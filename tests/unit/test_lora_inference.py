from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.app.lora.inference import select_lora_adapter
from backend.app.lora.registry import ModelRegistry, ModelRegistryEntry


def _tmp_path() -> Path:
    path = Path(".tmp_tests") / f"{uuid4().hex}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_select_lora_adapter_returns_active_passed_adapter_for_task() -> None:
    registry = ModelRegistry(_tmp_path())
    registry.add_model(
        ModelRegistryEntry(
            model_id="slot_v1",
            version="2026-05-19",
            adapter_path="C:/tmp/lora_adapters/slot_v1",
            task_type="slot_extraction",
            safety_gate_status="passed",
        )
    )
    registry.enable_inference("slot_v1", enabled=True)

    adapter = select_lora_adapter("slot_extraction", registry)

    assert adapter is not None
    assert adapter.model_id == "slot_v1"


def test_select_lora_adapter_ignores_disabled_or_failed_adapters() -> None:
    registry = ModelRegistry(_tmp_path())
    registry.add_model(
        ModelRegistryEntry(
            model_id="disabled",
            version="2026-05-19",
            adapter_path="C:/tmp/lora_adapters/disabled",
            task_type="slot_extraction",
            safety_gate_status="passed",
        )
    )
    registry.add_model(
        ModelRegistryEntry(
            model_id="failed",
            version="2026-05-19",
            adapter_path="C:/tmp/lora_adapters/failed",
            task_type="slot_extraction",
            safety_gate_status="failed",
        )
    )

    assert select_lora_adapter("slot_extraction", registry) is None
