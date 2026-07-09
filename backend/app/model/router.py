from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.agent.safety_precheck import SafetyLevel
from backend.app.core.config import Settings
from backend.app.model.router_policy import RouterPolicy
from backend.app.services.feature_flag_service import FeatureFlagService


ModelName = Literal["primary", "local_small"]
ModelTaskType = Literal[
    "final_answer",
    "intent_routing",
    "query_normalization",
    "structured_extraction",
    "measurement_analysis",
    "summarization",
]
ModelRouteMode = Literal["disabled", "primary", "shadow", "takeover"]


class ModelRouteRequest(BaseModel):
    task_type: ModelTaskType
    safety_level: SafetyLevel = "S0"
    requires_final_answer: bool = False
    user_query: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ModelRouteDecision(BaseModel):
    selected_model: ModelName
    route_mode: ModelRouteMode
    shadow_model: ModelName | None = None
    local_candidate_allowed: bool = False
    blocked_reason: str | None = None
    reason: str = ""


class ModelRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.flags = FeatureFlagService(self.settings)
        self.policy = RouterPolicy(self.settings)

    def route(self, request: ModelRouteRequest) -> ModelRouteDecision:
        local_candidate_allowed, blocked_reason = self.policy.is_local_takeover_allowed(request)

        if not self.flags.model_router_enabled:
            return ModelRouteDecision(
                selected_model="primary",
                route_mode="disabled",
                local_candidate_allowed=local_candidate_allowed,
                blocked_reason=blocked_reason,
                reason="model router disabled",
            )

        if self.flags.model_router_shadow_mode:
            return ModelRouteDecision(
                selected_model="primary",
                route_mode="shadow",
                shadow_model="local_small" if self.flags.local_model_enabled and local_candidate_allowed else None,
                local_candidate_allowed=local_candidate_allowed,
                blocked_reason=blocked_reason,
                reason="shadow mode keeps primary as actual model",
            )

        if (
            self.flags.model_router_low_risk_takeover_enabled
            and self.flags.local_model_enabled
            and local_candidate_allowed
        ):
            return ModelRouteDecision(
                selected_model="local_small",
                route_mode="takeover",
                local_candidate_allowed=True,
                reason="low-risk local model takeover enabled",
            )

        return ModelRouteDecision(
            selected_model="primary",
            route_mode="primary",
            local_candidate_allowed=local_candidate_allowed,
            blocked_reason=blocked_reason,
            reason="primary model required",
        )
