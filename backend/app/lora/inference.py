from __future__ import annotations

from backend.app.lora.dataset import LoraTaskType
from backend.app.lora.registry import ModelRegistry, ModelRegistryEntry


class LoraInferenceClient:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def select_adapter(self, task_type: LoraTaskType) -> ModelRegistryEntry | None:
        return select_lora_adapter(task_type, self.registry)


def select_lora_adapter(task_type: LoraTaskType, registry: ModelRegistry) -> ModelRegistryEntry | None:
    for entry in registry.active_inference_models():
        if entry.task_type == task_type:
            return entry
    return None
