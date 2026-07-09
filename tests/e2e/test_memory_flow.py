from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.app.agent.graph import run_disease_graph, run_measurement_graph
from backend.app.core.config import Settings
from backend.app.db.repositories import MemoryRepository
from backend.app.main import create_app
from backend.app.schemas.measurement import MeasurementInput
from backend.app.services.memory_service import MemoryEvent, MemoryService


def test_measurement_api_does_not_write_memory_when_flag_disabled() -> None:
    client = TestClient(create_app(settings=Settings(database={"url": "sqlite:///:memory:"})))

    response = client.post(
        "/api/measurement/analyze",
        json={"animal_id": "yak_032", "current": {"chest_girth_cm": 158.4}, "confidence": 0.82},
    )

    assert response.json()["code"] == 0
    repository = MemoryRepository(client.app.state.db_conn)
    assert repository.get_projection("animal", "yak_032") == {}


def test_measurement_api_writes_user_confirmed_measurement_memory_when_enabled() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        v3={"enabled": True},
        long_term_memory={"write_enabled": True},
    )
    client = TestClient(create_app(settings=settings))

    response = client.post(
        "/api/measurement/analyze",
        json={"animal_id": "yak_032", "current": {"chest_girth_cm": 158.4}, "confidence": 0.82},
    )

    assert response.json()["code"] == 0
    repository = MemoryRepository(client.app.state.db_conn)
    projection = repository.get_projection("animal", "yak_032")
    assert projection["measurement"]["current"] == {"chest_girth_cm": 158.4}
    assert projection["measurement"]["confidence"] == 0.82
    assert "abnormal_items" not in projection["measurement"]
    assert "report" not in projection["measurement"]


def test_measurement_graph_calls_maybe_write_memory_without_changing_report() -> None:
    settings = Settings(v3={"enabled": True}, long_term_memory={"write_enabled": True})
    written: list[MemoryEvent] = []
    measurement = MeasurementInput(
        animal_id="yak_032",
        current={"chest_girth_cm": 158.4, "weight_kg": 246.5},
        history=[{"measure_date": "2026-04-01", "chest_girth_cm": 157.0, "weight_kg": 242.0}],
        confidence=0.82,
    )

    state = asyncio.run(
        run_measurement_graph(
            measurement,
            session_id="s_measure_memory",
            memory_service=MemoryService(event_writer=written.append),
            settings=settings,
        )
    )

    assert state.measurement_report is not None
    assert written[0].payload["fact_type"] == "measurement"
    assert written[0].payload["value"]["current"] == {"chest_girth_cm": 158.4, "weight_kg": 246.5}
    assert "abnormal_items" not in written[0].payload["value"]
    assert "report" not in written[0].payload["value"]
    assert state.tool_results["long_term_memory"][0]["fact_type"] == "measurement"


def test_disease_graph_writes_user_confirmed_facts_without_diagnosis_memory() -> None:
    settings = Settings(v3={"enabled": True}, long_term_memory={"write_enabled": True})
    written: list[MemoryEvent] = []

    asyncio.run(
        run_disease_graph(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
            session_id="s_disease_memory",
            animal_id="yak_032",
            memory_service=MemoryService(event_writer=written.append),
            settings=settings,
        )
    )

    event = written[0]
    assert event.payload["fact_type"] == "user_confirmed_observation"
    assert event.payload["value"]["case_summary"] == "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病"
    assert "risk_level" not in event.payload["value"]
    assert "diagnosis" not in event.payload["value"]
    assert "recommendation" not in event.payload["value"]
