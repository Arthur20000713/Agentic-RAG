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
        task_type="measurement_analysis",
        safety_level="S1",
        user_query="analyze measurement structure",
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
    assert row["task_type"] == "measurement_analysis"
    assert row["safety_level"] == "S1"
    assert row["selected_model"] == "primary"
    assert row["route_mode"] == "shadow"
    assert row["shadow_model"] == "local_small"
    assert row["local_candidate_allowed"] is True
    assert row["route_request"]["metadata"]["animal_id"] == "yak_032"
    assert row["route_decision"]["shadow_model"] == "local_small"

    rows = repository.list_by_request_id("req_shadow")
    assert [item["id"] for item in rows] == [log_id]


def test_model_route_log_repository_persists_takeover_fallback_fields() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    repository = ModelRouteLogRepository(conn)

    log_id = repository.create(
        session_id="s_takeover",
        request_id="req_takeover",
        route_request={
            "task_type": "measurement_analysis",
            "safety_level": "S1",
            "requires_final_answer": False,
        },
        route_decision={
            "selected_model": "local_small",
            "route_mode": "takeover",
            "shadow_model": None,
            "local_candidate_allowed": True,
            "blocked_reason": None,
            "reason": "low-risk local model takeover enabled",
            "fallback_required": True,
            "fallback_reason": "LOCAL_MODEL_SCHEMA_ERROR",
            "latency_ms": 87,
            "model_version": "qwen2.5:7b-instruct",
        },
    )

    row = repository.get(log_id)

    assert row is not None
    assert row["route_mode"] == "takeover"
    assert row["fallback_required"] is True
    assert row["fallback_reason"] == "LOCAL_MODEL_SCHEMA_ERROR"
    assert row["latency_ms"] == 87
    assert row["model_version"] == "qwen2.5:7b-instruct"
    assert row["route_decision"]["fallback_required"] is True


def test_model_route_log_migration_adds_v5_columns_to_existing_table() -> None:
    conn = get_connection("sqlite:///:memory:")
    conn.execute(
        """
        CREATE TABLE model_route_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            request_id TEXT,
            task_type TEXT NOT NULL,
            safety_level TEXT,
            selected_model TEXT NOT NULL,
            route_mode TEXT NOT NULL,
            shadow_model TEXT,
            local_candidate_allowed INTEGER DEFAULT 0,
            blocked_reason TEXT,
            reason TEXT,
            route_request_json TEXT NOT NULL,
            route_decision_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    init_db(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(model_route_log)").fetchall()}
    assert {"fallback_required", "fallback_reason", "latency_ms", "model_version"}.issubset(columns)
