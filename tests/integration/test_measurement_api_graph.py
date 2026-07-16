from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

import backend.app.api.measurement as measurement_api
from backend.app.core.config import Settings
from backend.app.db.repositories import (
    AnimalRecord,
    AnimalRepository,
    MeasurementRepository,
)
from backend.app.main import create_app
from backend.app.schemas.measurement import MeasurementInput


def test_measurement_api_prepares_repository_history_before_running_graph(
    monkeypatch,
) -> None:
    settings = Settings(database={"url": "sqlite:///:memory:"})
    app = create_app(settings=settings)
    AnimalRepository(app.state.db_conn).upsert(AnimalRecord(animal_id="yak_032"))
    MeasurementRepository(app.state.db_conn).add(
        animal_id="yak_032",
        measure_date="2026-04-01",
        values={"chest_girth_cm": 157.0},
    )
    captured: dict[str, Any] = {}

    async def fake_run_measurement_graph(
        measurement: MeasurementInput,
        **kwargs: Any,
    ) -> SimpleNamespace:
        captured["measurement"] = measurement
        captured.update(kwargs)
        return SimpleNamespace(
            measurement_report={
                "animal_id": measurement.animal_id,
                "summary": "graph result",
                "abnormal_items": [],
                "evidence": [],
                "recommendation": "continue monitoring",
                "report": "graph result",
                "used_demo_history": False,
            }
        )

    monkeypatch.setattr(
        measurement_api,
        "run_measurement_graph",
        fake_run_measurement_graph,
    )

    response = TestClient(app).post(
        "/api/measurement/analyze",
        json={
            "animal_id": "yak_032",
            "current": {"chest_girth_cm": 158.4},
            "confidence": 0.82,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["report"] == "graph result"
    prepared = captured["measurement"]
    assert prepared.history[0].chest_girth_cm == 157.0
    assert captured["settings"] is settings
    assert captured["memory_service"] is None
