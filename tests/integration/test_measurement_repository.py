from __future__ import annotations

from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import AnimalRecord, AnimalRepository, MeasurementRepository


def test_measurement_repository_lists_history_by_animal_id() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    AnimalRepository(conn).upsert(AnimalRecord(animal_id="yak_001", species="yak"))

    repo = MeasurementRepository(conn)
    repo.add(
        animal_id="yak_001",
        measure_date="2026-05-01",
        values={"body_height_cm": 113.2, "weight_kg": 240.0},
        source="manual",
        confidence=0.9,
    )

    history = repo.list_history("yak_001")

    assert len(history) == 1
    assert history[0]["body_height_cm"] == 113.2
    assert history[0]["source"] == "manual"

