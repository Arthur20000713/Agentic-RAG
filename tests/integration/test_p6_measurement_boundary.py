from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from backend.app.core.config import Settings, load_settings
from backend.app.main import create_app


SERVICE_TOKEN = "test-java-service-token-32-characters"
BUSINESS_TABLES = {
    "farm_profile",
    "animal_profile",
    "body_measurement_record",
    "memory_event",
    "farm_memory",
    "animal_memory",
}


def _deny_business_table_access(
    action: int,
    table: str | None,
    _column: str | None,
    _database: str | None,
    _trigger: str | None,
) -> int:
    guarded_actions = {
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
    }
    if action in guarded_actions and table in BUSINESS_TABLES:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _internal_settings() -> Settings:
    return Settings(
        database={"url": "sqlite:///:memory:"},
        internal_api={
            "service_token": SERVICE_TOKEN,
            "execution_database_url": "sqlite:///:memory:",
            "ingestion_worker_enabled": False,
        },
    )


def test_legacy_measurement_is_disabled_by_default_and_in_compose() -> None:
    assert Settings().legacy_api.measurement_enabled is False
    assert (
        load_settings("config/settings.compose.yaml").legacy_api.measurement_enabled
        is False
    )

    app = create_app(settings=_internal_settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/measurement/analyze",
            json={"animal_id": "animal_boundary", "current": {"weight_kg": 210}},
        )
        paths = client.get("/openapi.json").json()["paths"]

    assert response.status_code == 404
    assert "/api/measurement/analyze" not in paths


def test_internal_snapshot_measurement_never_accesses_business_tables() -> None:
    app = create_app(settings=_internal_settings())
    app.state.db_conn.set_authorizer(_deny_business_table_access)
    app.state.execution_db_conn.set_authorizer(_deny_business_table_access)
    request_id = "req_boundary_0001"
    with TestClient(app) as client:
        try:
            response = client.post(
                "/internal/v1/ai/measurements/analyze",
                headers={
                    "Authorization": f"Bearer {SERVICE_TOKEN}",
                    "X-Request-ID": request_id,
                    "Idempotency-Key": "idem_boundary_0001",
                },
                json={
                    "requestId": request_id,
                    "operationId": "op_boundary_0001",
                    "userId": "user_boundary_0001",
                    "animalSnapshot": {
                        "animalId": "animal_boundary_0001",
                        "species": "cattle",
                        "breed": "Holstein",
                    },
                    "ageMonth": 18,
                    "current": {"weightKg": 210.0, "chestGirthCm": 121.0},
                    "history": [
                        {
                            "measureDate": "2026-07-01",
                            "weightKg": 205.0,
                            "chestGirthCm": 120.0,
                        }
                    ],
                    "confidence": 0.92,
                    "deadlineMs": 10000,
                },
            )
        finally:
            app.state.db_conn.set_authorizer(None)
            app.state.execution_db_conn.set_authorizer(None)

    assert response.status_code == 200
    body = response.json()
    assert body["operationId"] == "op_boundary_0001"
    assert body["result"]["animalId"] == "animal_boundary_0001"
