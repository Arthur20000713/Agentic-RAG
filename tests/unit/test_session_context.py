from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.services.session_context_service import SessionContextData, SessionContextService


def _service(now: datetime | None = None) -> SessionContextService:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    return SessionContextService(conn, now_provider=lambda: now or datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc))


def test_session_context_service_saves_and_reads_context() -> None:
    service = _service()
    context = SessionContextData(
        session_id="s1",
        last_intent="disease_consultation",
        last_species="cattle",
        last_symptoms=["diarrhea"],
        pending_slots=["temperature_c"],
        slot_sources={"temperature_c": "missing"},
        risk_context_status="incomplete",
    )

    saved = service.save_context(context)
    loaded = service.get_context("s1")

    assert loaded == saved
    assert loaded is not None
    assert loaded.session_id == "s1"
    assert loaded.last_intent == "disease_consultation"
    assert loaded.pending_slots == ["temperature_c"]
    assert loaded.updated_at == datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)


def test_session_context_service_updates_existing_context() -> None:
    service = _service()
    service.save_context(SessionContextData(session_id="s1", pending_slots=["temperature_c"]))

    updated = service.update_context(
        "s1",
        pending_slots=[],
        slot_sources={"temperature_c": "user_confirmed"},
        risk_context_status="complete",
    )

    assert updated.pending_slots == []
    assert updated.slot_sources == {"temperature_c": "user_confirmed"}
    assert updated.risk_context_status == "complete"
    assert service.get_context("s1") == updated


def test_session_context_service_update_creates_missing_context() -> None:
    service = _service()

    updated = service.update_context("s_new", last_animal_id="yak_032")

    assert updated.session_id == "s_new"
    assert updated.last_animal_id == "yak_032"
    assert service.get_context("s_new") == updated


def test_session_context_slot_sources_accept_only_allowed_values() -> None:
    context = SessionContextData(
        session_id="s1",
        slot_sources={
            "duration_days": "user_confirmed",
            "risk_level": "ai_inferred",
            "temperature_c": "missing",
            "group_outbreak": "stale",
            "symptoms": "tool_result",
        },
    )

    assert context.slot_sources["duration_days"] == "user_confirmed"

    with pytest.raises(ValidationError):
        SessionContextData(session_id="s1", slot_sources={"temperature_c": "guessed"})


def test_session_context_service_set_slot_source_validates_value() -> None:
    service = _service()
    service.save_context(SessionContextData(session_id="s1"))

    updated = service.set_slot_source("s1", "temperature_c", "user_confirmed")

    assert updated.slot_sources == {"temperature_c": "user_confirmed"}
    with pytest.raises(ValidationError):
        service.update_context("s1", slot_sources={"temperature_c": "guessed"})
