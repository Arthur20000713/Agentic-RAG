from __future__ import annotations

from pydantic import BaseModel

from backend.app.core.config import Settings


class FeatureFlagSnapshot(BaseModel):
    v3_enabled: bool
    model_router_enabled: bool
    model_router_shadow_mode: bool
    model_router_low_risk_takeover_enabled: bool
    local_model_enabled: bool
    lora_dataset_enabled: bool
    lora_inference_enabled: bool
    memory_write_enabled: bool
    memory_read_enabled: bool
    safety_precheck_enabled: bool
    final_guard_required: bool


class FeatureFlagService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def snapshot(self) -> FeatureFlagSnapshot:
        return FeatureFlagSnapshot(
            v3_enabled=self.v3_enabled,
            model_router_enabled=self.model_router_enabled,
            model_router_shadow_mode=self.model_router_shadow_mode,
            model_router_low_risk_takeover_enabled=self.model_router_low_risk_takeover_enabled,
            local_model_enabled=self.local_model_enabled,
            lora_dataset_enabled=self.lora_dataset_enabled,
            lora_inference_enabled=self.lora_inference_enabled,
            memory_write_enabled=self.memory_write_enabled,
            memory_read_enabled=self.memory_read_enabled,
            safety_precheck_enabled=self.safety_precheck_enabled,
            final_guard_required=self.final_guard_required,
        )

    @property
    def v3_enabled(self) -> bool:
        return self.settings.v3.enabled

    @property
    def model_router_enabled(self) -> bool:
        return self.v3_enabled and self.settings.model_router.enabled

    @property
    def model_router_shadow_mode(self) -> bool:
        return self.model_router_enabled and self.settings.model_router.shadow_mode

    @property
    def model_router_low_risk_takeover_enabled(self) -> bool:
        return (
            self.model_router_enabled
            and self.settings.model_router.allow_low_risk_takeover
            and not self.settings.model_router.shadow_mode
        )

    @property
    def local_model_enabled(self) -> bool:
        return self.v3_enabled and self.settings.local_model.enabled

    @property
    def lora_dataset_enabled(self) -> bool:
        return self.v3_enabled and self.settings.lora.dataset_enabled

    @property
    def lora_inference_enabled(self) -> bool:
        return self.v3_enabled and self.settings.lora.inference_enabled

    @property
    def memory_write_enabled(self) -> bool:
        return self.v3_enabled and self.settings.long_term_memory.write_enabled

    @property
    def memory_read_enabled(self) -> bool:
        return self.v3_enabled and self.settings.long_term_memory.read_enabled

    @property
    def safety_precheck_enabled(self) -> bool:
        return self.v3_enabled and self.settings.enhanced_safety.precheck_enabled

    @property
    def final_guard_required(self) -> bool:
        return self.settings.enhanced_safety.final_guard_required
