from __future__ import annotations

from pydantic import BaseModel

from backend.app.core.config import Settings


class FeatureFlagSnapshot(BaseModel):
    agent_runtime_engine: str
    model_router_enabled: bool
    model_router_shadow_mode: bool
    model_router_low_risk_takeover_enabled: bool
    local_model_enabled: bool
    primary_llm_enabled: bool
    disease_llm_enabled: bool
    disease_llm_shadow_mode: bool
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
            agent_runtime_engine=self.agent_runtime_engine,
            model_router_enabled=self.model_router_enabled,
            model_router_shadow_mode=self.model_router_shadow_mode,
            model_router_low_risk_takeover_enabled=self.model_router_low_risk_takeover_enabled,
            local_model_enabled=self.local_model_enabled,
            primary_llm_enabled=self.primary_llm_enabled,
            disease_llm_enabled=self.disease_llm_enabled,
            disease_llm_shadow_mode=self.disease_llm_shadow_mode,
            lora_dataset_enabled=self.lora_dataset_enabled,
            lora_inference_enabled=self.lora_inference_enabled,
            memory_write_enabled=self.memory_write_enabled,
            memory_read_enabled=self.memory_read_enabled,
            safety_precheck_enabled=self.safety_precheck_enabled,
            final_guard_required=self.final_guard_required,
        )

    @property
    def agent_runtime_engine(self) -> str:
        return self.settings.agent_runtime.engine

    @property
    def model_router_enabled(self) -> bool:
        return self.settings.model_router.enabled

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
        return self.settings.local_model.enabled

    @property
    def primary_llm_enabled(self) -> bool:
        return self.settings.primary_llm.enabled

    @property
    def disease_llm_enabled(self) -> bool:
        return self.settings.disease_llm.enabled

    @property
    def disease_llm_shadow_mode(self) -> bool:
        return self.disease_llm_enabled and self.settings.disease_llm.shadow_mode

    @property
    def lora_dataset_enabled(self) -> bool:
        return self.settings.lora.dataset_enabled

    @property
    def lora_inference_enabled(self) -> bool:
        return self.settings.lora.inference_enabled

    @property
    def memory_write_enabled(self) -> bool:
        return self.settings.long_term_memory.write_enabled

    @property
    def memory_read_enabled(self) -> bool:
        return self.settings.long_term_memory.read_enabled

    @property
    def safety_precheck_enabled(self) -> bool:
        return self.settings.enhanced_safety.precheck_enabled

    @property
    def final_guard_required(self) -> bool:
        return self.settings.enhanced_safety.final_guard_required
