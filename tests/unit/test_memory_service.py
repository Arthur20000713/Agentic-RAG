from __future__ import annotations

from backend.app.services.memory_service import MemoryEvent, MemoryFact, MemoryService


def test_memory_service_writes_user_confirmed_fact() -> None:
    written: list[MemoryEvent] = []
    service = MemoryService(event_writer=written.append)
    fact = MemoryFact(
        subject_type="animal",
        subject_id="yak_032",
        fact_type="profile",
        value={"species": "yak"},
        source="user_confirmed",
    )

    event = service.maybe_write_memory(fact)

    assert event is not None
    assert event.source == "user_confirmed"
    assert event.payload["fact_type"] == "profile"
    assert event.payload["value"] == {"species": "yak"}
    assert written == [event]


def test_memory_service_writes_tool_result_fact() -> None:
    service = MemoryService()
    fact = MemoryFact(
        subject_type="animal",
        subject_id="yak_032",
        fact_type="measurement",
        value={"chest_girth_cm": 158.4},
        source="tool_result",
        metadata={"tool_name": "body_measurement_analyzer"},
    )

    event = service.maybe_write_memory(fact)

    assert event is not None
    assert event.source == "tool_result"
    assert event.payload["metadata"] == {"tool_name": "body_measurement_analyzer"}


def test_memory_service_skips_ai_inferred_fact() -> None:
    written: list[MemoryEvent] = []
    service = MemoryService(event_writer=written.append)
    fact = MemoryFact(
        subject_type="animal",
        subject_id="yak_032",
        fact_type="diagnosis",
        value={"diagnosis": "pneumonia"},
        source="ai_inferred",
    )

    event = service.maybe_write_memory(fact)

    assert event is None
    assert written == []
