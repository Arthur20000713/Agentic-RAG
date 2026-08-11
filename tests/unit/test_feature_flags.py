from __future__ import annotations

from backend.app.core.config import Settings, load_settings
from backend.app.services.feature_flag_service import FeatureFlagService


def test_feature_flags_default_to_optional_features_disabled() -> None:
    service = FeatureFlagService(load_settings("config/settings.test.yaml"))
    snapshot = service.snapshot()

    assert snapshot.agent_runtime_engine == "langgraph"
    assert snapshot.model_router_enabled is False
    assert snapshot.model_router_shadow_mode is False
    assert snapshot.model_router_low_risk_takeover_enabled is False
    assert snapshot.local_model_enabled is False
    assert snapshot.primary_llm_enabled is False
    assert snapshot.disease_llm_enabled is False
    assert snapshot.lora_dataset_enabled is False
    assert snapshot.lora_inference_enabled is False
    assert snapshot.memory_write_enabled is False
    assert snapshot.memory_read_enabled is False
    assert snapshot.safety_precheck_enabled is True
    assert snapshot.final_guard_required is True


def test_sub_feature_flags_follow_their_own_settings() -> None:
    settings = Settings(
        model_router={"enabled": True, "shadow_mode": True, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
        primary_llm={"enabled": True},
        disease_llm={"enabled": True},
        lora={"dataset_enabled": True, "inference_enabled": True},
        long_term_memory={"write_enabled": True, "read_enabled": True},
        enhanced_safety={"precheck_enabled": True, "final_guard_required": True},
    )
    snapshot = FeatureFlagService(settings).snapshot()

    assert snapshot.agent_runtime_engine == "langgraph"
    assert snapshot.model_router_enabled is True
    assert snapshot.local_model_enabled is True
    assert snapshot.primary_llm_enabled is True
    assert snapshot.disease_llm_enabled is True
    assert snapshot.lora_dataset_enabled is True
    assert snapshot.lora_inference_enabled is True
    assert snapshot.memory_write_enabled is True
    assert snapshot.memory_read_enabled is True
    assert snapshot.safety_precheck_enabled is True


def test_feature_flags_enable_shadow_without_takeover() -> None:
    settings = Settings(
        model_router={"enabled": True, "shadow_mode": True, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
        lora={"dataset_enabled": True, "inference_enabled": False},
        long_term_memory={"write_enabled": True, "read_enabled": False},
        enhanced_safety={"precheck_enabled": True, "final_guard_required": True},
    )
    snapshot = FeatureFlagService(settings).snapshot()

    assert snapshot.agent_runtime_engine == "langgraph"
    assert snapshot.model_router_enabled is True
    assert snapshot.model_router_shadow_mode is True
    assert snapshot.model_router_low_risk_takeover_enabled is False
    assert snapshot.local_model_enabled is True
    assert snapshot.lora_dataset_enabled is True
    assert snapshot.lora_inference_enabled is False
    assert snapshot.memory_write_enabled is True
    assert snapshot.memory_read_enabled is False
    assert snapshot.safety_precheck_enabled is True


def test_feature_flags_allow_low_risk_takeover_only_outside_shadow_mode() -> None:
    settings = Settings(
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
    )

    service = FeatureFlagService(settings)

    assert service.model_router_enabled is True
    assert service.model_router_shadow_mode is False
    assert service.model_router_low_risk_takeover_enabled is True
