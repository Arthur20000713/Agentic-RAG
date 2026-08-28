from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from backend.app.agent.memory_store import RepositoryMemoryStore
from backend.app.agent.memory_tools import search_memory, write_memory
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import MemoryRepository


def _store(*, clock=None):  # noqa: ANN001, ANN202
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    return conn, RepositoryMemoryStore(MemoryRepository(conn), clock=clock)


def test_write_and_search_animal_profile() -> None:
    _, store = _store()

    async def run() -> None:
        result = await write_memory(
            store,
            user_id="user_a",
            subject_type="animal",
            subject_id="yak_032",
            memory_type="animal_profile",
            content={"species": "yak", "breed": "plateau"},
            source="tool_result",
            session_id="session_a",
            ttl_days=365,
        )
        found = await search_memory(
            store,
            user_id="user_a",
            subject_type="animal",
            subject_id="yak_032",
        )

        assert result.status == "written"
        assert result.record.record_id == "animal_profile"
        assert found == [result.record]

    asyncio.run(run())


def test_write_memory_is_idempotent_for_same_operation() -> None:
    conn, store = _store()

    async def run() -> None:
        kwargs = {
            "user_id": "user_a",
            "subject_type": "animal",
            "subject_id": "yak_032",
            "memory_type": "consultation",
            "content": {"observations": ["diarrhea", "reduced appetite"]},
            "source": "user_confirmed",
            "session_id": "session_a",
            "operation_id": "turn_001",
        }
        first = await write_memory(store, **kwargs)
        second = await write_memory(store, **kwargs)
        assert first.status == "written"
        assert second.status == "unchanged"

    asyncio.run(run())
    assert conn.execute("SELECT COUNT(*) AS count FROM memory_event").fetchone()["count"] == 1


def test_profile_correction_supersedes_previous_record() -> None:
    conn, store = _store()

    async def run() -> None:
        common = {
            "store": store,
            "user_id": "user_a",
            "subject_type": "animal",
            "subject_id": "yak_032",
            "memory_type": "animal_profile",
            "source": "tool_result",
        }
        await write_memory(content={"species": "yak"}, **common)
        corrected = await write_memory(content={"species": "cattle"}, **common)
        found = await search_memory(
            store,
            user_id="user_a",
            subject_type="animal",
            subject_id="yak_032",
            memory_types={"animal_profile"},
        )
        assert corrected.status == "written"
        assert [item.content["species"] for item in found] == ["cattle"]

    asyncio.run(run())
    events = conn.execute("SELECT event_type FROM memory_event ORDER BY id").fetchall()
    assert [row["event_type"] for row in events] == ["upsert", "supersede"]


def test_write_memory_rejects_untrusted_or_medical_conclusions() -> None:
    _, store = _store()

    async def run() -> None:
        invalid_cases = (
            {"memory_type": "observation", "content": {"sign": "cough"}, "source": "ai_inferred"},
            {"memory_type": "consultation", "content": {"diagnosis": "pneumonia"}, "source": "user_confirmed"},
            {"memory_type": "consultation", "content": {"nested": {"treatment": "antibiotic"}}, "source": "tool_result"},
        )
        for case in invalid_cases:
            try:
                await write_memory(
                    store,
                    user_id="user_a",
                    subject_type="animal",
                    subject_id="yak_032",
                    **case,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("unsafe memory should be rejected")

    asyncio.run(run())


def test_search_memory_filters_type_query_tenant_and_ttl() -> None:
    now = [datetime(2026, 8, 28, tzinfo=UTC)]
    _, store = _store(clock=lambda: now[0])

    async def run() -> None:
        await write_memory(
            store,
            user_id="user_a",
            subject_type="animal",
            subject_id="yak_032",
            memory_type="consultation",
            content={"observations": ["calf diarrhea"]},
            source="user_confirmed",
            operation_id="turn_1",
            ttl_days=1,
        )
        await write_memory(
            store,
            user_id="user_b",
            subject_type="animal",
            subject_id="yak_032",
            memory_type="consultation",
            content={"observations": ["calf diarrhea"]},
            source="user_confirmed",
            operation_id="turn_2",
        )
        matches = await search_memory(
            store,
            user_id="user_a",
            subject_type="animal",
            subject_id="yak_032",
            query="diarrhea",
            memory_types={"consultation"},
            limit=1,
        )
        assert [item.record_id for item in matches] == ["consultation:turn_1"]

        now[0] += timedelta(days=1)
        expired = await search_memory(
            store,
            user_id="user_a",
            subject_type="animal",
            subject_id="yak_032",
        )
        assert expired == []

    asyncio.run(run())
