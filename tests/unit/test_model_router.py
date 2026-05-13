from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.model.router import ModelRouteDecision, ModelRouteRequest, ModelRouter


def test_model_route_request_and_decision_schema_are_stable() -> None:
    request = ModelRouteRequest(
        task_type="structured_extraction",
        safety_level="S1",
        user_query="extract body measurement slots",
        metadata={"session_id": "s1"},
    )
    decision = ModelRouter().route(request)

    assert isinstance(decision, ModelRouteDecision)
    assert request.model_dump() == {
        "task_type": "structured_extraction",
        "safety_level": "S1",
        "requires_final_answer": False,
        "user_query": "extract body measurement slots",
        "metadata": {"session_id": "s1"},
    }
    assert set(decision.model_dump()) == {
        "selected_model",
        "route_mode",
        "shadow_model",
        "local_candidate_allowed",
        "blocked_reason",
        "reason",
    }


def test_model_router_disabled_keeps_primary_model() -> None:
    decision = ModelRouter(Settings()).route(
        ModelRouteRequest(task_type="structured_extraction", safety_level="S1")
    )

    assert decision.selected_model == "primary"
    assert decision.route_mode == "disabled"
    assert decision.shadow_model is None
    assert decision.local_candidate_allowed is True


def test_model_router_shadow_records_local_small_without_takeover() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": True, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )

    decision = ModelRouter(settings).route(
        ModelRouteRequest(task_type="structured_extraction", safety_level="S1")
    )

    assert decision.selected_model == "primary"
    assert decision.route_mode == "shadow"
    assert decision.shadow_model == "local_small"
    assert decision.local_candidate_allowed is True


def test_model_router_takeover_allows_only_low_risk_structured_tasks() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )

    decision = ModelRouter(settings).route(
        ModelRouteRequest(task_type="measurement_analysis", safety_level="S1")
    )

    assert decision.selected_model == "local_small"
    assert decision.route_mode == "takeover"
    assert decision.local_candidate_allowed is True


def test_model_router_allows_s2_structured_extraction_but_not_final_answer() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )

    extraction = ModelRouter(settings).route(
        ModelRouteRequest(task_type="structured_extraction", safety_level="S2")
    )
    final_answer = ModelRouter(settings).route(
        ModelRouteRequest(task_type="final_answer", safety_level="S2", requires_final_answer=True)
    )

    assert extraction.selected_model == "local_small"
    assert extraction.local_candidate_allowed is True
    assert final_answer.selected_model == "primary"
    assert final_answer.local_candidate_allowed is False


def test_model_router_never_routes_high_risk_to_local_small() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )

    decision = ModelRouter(settings).route(
        ModelRouteRequest(task_type="final_answer", safety_level="S3", requires_final_answer=True)
    )

    assert decision.selected_model == "primary"
    assert decision.route_mode == "primary"
    assert decision.shadow_model is None
    assert decision.local_candidate_allowed is False
    assert decision.blocked_reason == "high_risk_requires_primary"


def test_model_router_keeps_disease_final_answer_on_primary() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )

    decision = ModelRouter(settings).route(
        ModelRouteRequest(task_type="final_answer", safety_level="S2", requires_final_answer=True)
    )

    assert decision.selected_model == "primary"
    assert decision.local_candidate_allowed is False
    assert decision.blocked_reason == "risk_final_answer_requires_primary"
