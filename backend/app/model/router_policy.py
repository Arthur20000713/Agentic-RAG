from __future__ import annotations

from typing import TYPE_CHECKING

from backend.app.core.config import Settings

if TYPE_CHECKING:
    from backend.app.model.router import ModelRouteRequest


LOW_RISK_LEVELS = {"S0", "S1", "S2"}
HIGH_RISK_LEVELS = {"S3", "S4"}


class RouterPolicy:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def is_local_takeover_allowed(self, request: ModelRouteRequest) -> tuple[bool, str | None]:
        return is_local_takeover_allowed(request, self.settings)


def is_local_takeover_allowed(request: ModelRouteRequest, settings: Settings) -> tuple[bool, str | None]:
    safety_block = blocked_by_safety(request)
    if safety_block:
        return False, safety_block

    if request.safety_level in set(settings.model_router.blocked_safety_levels):
        return False, "blocked_safety_level_requires_primary"

    if request.requires_final_answer:
        if request.safety_level in {"S2", "S3", "S4"}:
            return False, "risk_final_answer_requires_primary"
        return False, "final_answer_requires_primary"

    if request.safety_level not in LOW_RISK_LEVELS:
        return False, "safety_level_not_low_risk"

    if request.task_type not in set(settings.model_router.takeover_task_types):
        return False, "task_type_not_enabled_for_local_takeover"

    return True, None


def blocked_by_safety(request: ModelRouteRequest) -> str | None:
    if request.safety_level in HIGH_RISK_LEVELS:
        return "high_risk_requires_primary"
    return None
