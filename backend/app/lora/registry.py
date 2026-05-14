from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.core.config import PROJECT_ROOT
from backend.app.lora.dataset import LoraTaskType


class ModelRegistryEntry(BaseModel):
    model_id: str
    version: str
    adapter_path: str
    task_type: LoraTaskType
    enabled_for_inference: bool = False
    metrics: dict[str, float] = Field(default_factory=dict)


class ModelRegistry:
    def __init__(self, registry_path: str | Path) -> None:
        path = Path(registry_path)
        self.registry_path = path if path.is_absolute() else PROJECT_ROOT / path

    def list_models(self) -> list[ModelRegistryEntry]:
        return self._load_entries()

    def get_model(self, model_id: str) -> ModelRegistryEntry | None:
        for entry in self._load_entries():
            if entry.model_id == model_id:
                return entry
        return None

    def add_model(self, entry: ModelRegistryEntry) -> None:
        entries = [item for item in self._load_entries() if item.model_id != entry.model_id]
        entries.append(entry)
        self._save_entries(entries)

    def enable_inference(self, model_id: str, *, enabled: bool) -> None:
        entries = self._load_entries()
        found = False
        updated: list[ModelRegistryEntry] = []
        for entry in entries:
            if entry.model_id == model_id:
                found = True
                updated.append(entry.model_copy(update={"enabled_for_inference": enabled}))
            else:
                updated.append(entry)
        if not found:
            raise KeyError(model_id)
        self._save_entries(updated)

    def active_inference_models(self) -> list[ModelRegistryEntry]:
        return [entry for entry in self._load_entries() if entry.enabled_for_inference]

    def _load_entries(self) -> list[ModelRegistryEntry]:
        if not self.registry_path.exists():
            return []
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("model registry must be a JSON list")
        return [ModelRegistryEntry.model_validate(item) for item in payload]

    def _save_entries(self, entries: list[ModelRegistryEntry]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [entry.model_dump() for entry in sorted(entries, key=lambda item: item.model_id)]
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
