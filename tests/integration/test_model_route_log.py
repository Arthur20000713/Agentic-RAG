from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import ModelRouteLogRepository
from backend.app.model.router import ModelRouteRequest, ModelRouter


def test_model_route_log_repository_persists_shadow_decision() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": True, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )
    route_request = ModelRouteRequest(
        task_type="structured_extraction",
        safety_level="S1",
        user_query="extract measurement slots",
        metadata={"animal_id": "yak_032"},
    )
    route_decision = ModelRouter(settings).route(route_request)

    assert route_decision.route_mode == "shadow"
    assert route_decision.shadow_model == "local_small"

    repository = ModelRouteLogRepository(conn)
    log_id = repository.add(
        session_id="s_shadow",
        request_id="req_shadow",
        route_request=route_request,
        route_decision=route_decision,
    )

    row = repository.get(log_id)
    assert row is not None
    assert row["session_id"] == "s_shadow"
    assert row["request_id"] == "req_shadow"
    assert row["task_type"] == "structured_extraction"
    assert row["safety_level"] == "S1"
    assert row["selected_model"] == "primary"
    assert row["route_mode"] == "shadow"
    assert row["shadow_model"] == "local_small"
    assert row["local_candidate_allowed"] is True
    assert row["route_request"]["metadata"]["animal_id"] == "yak_032"
    assert row["route_decision"]["shadow_model"] == "local_small"

    rows = repository.list_by_request_id("req_shadow")
    assert [item["id"] for item in rows] == [log_id]
