from __future__ import annotations

from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import MemoryRepository
from backend.app.services.memory_service import MemoryEvent


def test_memory_repository_appends_event_and_updates_animal_projection() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    repository = MemoryRepository(conn)
    event = MemoryEvent(
        event_id="mem_animal_profile",
        subject_type="animal",
        subject_id="yak_032",
        event_type="upsert",
        source="user_confirmed",
        payload={"fact_type": "profile", "value": {"species": "yak"}, "metadata": {}},
    )

    row_id = repository.append_event(event)

    saved_event = repository.get_event("mem_animal_profile")
    assert row_id > 0
    assert saved_event is not None
    assert saved_event["payload"]["value"] == {"species": "yak"}
    assert repository.get_projection("animal", "yak_032") == {"profile": {"species": "yak"}}


def test_memory_repository_supersede_generates_new_event_without_updating_original() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    repository = MemoryRepository(conn)
    repository.append_event(
        MemoryEvent(
            event_id="mem_old_profile",
            subject_type="animal",
            subject_id="yak_032",
            event_type="upsert",
            source="user_confirmed",
            payload={"fact_type": "profile", "value": {"species": "yak"}, "metadata": {}},
        )
    )

    new_event = repository.supersede_fact(
        subject_type="animal",
        subject_id="yak_032",
        fact_type="profile",
        value={"species": "cattle"},
        source="user_confirmed",
        supersedes_event_id="mem_old_profile",
    )

    original_event = repository.get_event("mem_old_profile")
    saved_new_event = repository.get_event(new_event.event_id)
    event_count = conn.execute("SELECT COUNT(*) AS count FROM memory_event").fetchone()["count"]
    assert original_event is not None
    assert saved_new_event is not None
    assert original_event["payload"]["value"] == {"species": "yak"}
    assert saved_new_event["supersedes_event_id"] == "mem_old_profile"
    assert repository.get_projection("animal", "yak_032") == {"profile": {"species": "cattle"}}
    assert event_count == 2


def test_memory_repository_delete_generates_new_event_and_removes_projection_fact() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    repository = MemoryRepository(conn)
    repository.append_event(
        MemoryEvent(
            event_id="mem_measurement",
            subject_type="animal",
            subject_id="yak_032",
            event_type="upsert",
            source="tool_result",
            payload={"fact_type": "measurement", "value": {"weight_kg": 420}, "metadata": {}},
        )
    )

    delete_event = repository.delete_fact(
        subject_type="animal",
        subject_id="yak_032",
        fact_type="measurement",
        source="user_confirmed",
        supersedes_event_id="mem_measurement",
    )

    saved_delete_event = repository.get_event(delete_event.event_id)
    event_count = conn.execute("SELECT COUNT(*) AS count FROM memory_event").fetchone()["count"]
    assert saved_delete_event is not None
    assert saved_delete_event["event_type"] == "delete"
    assert saved_delete_event["supersedes_event_id"] == "mem_measurement"
    assert repository.get_projection("animal", "yak_032") == {}
    assert event_count == 2


def test_memory_repository_updates_farm_projection() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    repository = MemoryRepository(conn)
    event = MemoryEvent(
        event_id="mem_farm_profile",
        subject_type="farm",
        subject_id="farm_001",
        event_type="upsert",
        source="user_confirmed",
        payload={"fact_type": "profile", "value": {"location": "Qinghai"}, "metadata": {}},
    )

    repository.append_event(event)

    assert repository.get_projection("farm", "farm_001") == {"profile": {"location": "Qinghai"}}
