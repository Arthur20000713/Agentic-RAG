from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from backend.app.agent.memory_store import RepositoryMemoryStore, memory_namespace
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import MemoryRepository


def _store(*, clock=None):  # noqa: ANN001, ANN202
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    return conn, RepositoryMemoryStore(MemoryRepository(conn), clock=clock)


def test_store_put_get_update_and_delete_keep_append_only_history() -> None:
    conn, store = _store()
    namespace = memory_namespace("user_a", "animal", "yak_032")

    store.put(namespace, "profile", {"source": "user_confirmed", "species": "yak"})
    first = store.get(namespace, "profile")
    store.put(namespace, "profile", {"source": "user_confirmed", "species": "cattle"})
    second = store.get(namespace, "profile")
    store.delete(namespace, "profile")

    events = conn.execute(
        "SELECT event_type, supersedes_event_id FROM memory_event ORDER BY id"
    ).fetchall()
    assert first is not None and first.value["species"] == "yak"
    assert second is not None and second.value["species"] == "cattle"
    assert store.get(namespace, "profile") is None
    assert [row["event_type"] for row in events] == ["upsert", "supersede", "delete"]
    assert events[1]["supersedes_event_id"] == first.value["event_id"]
    assert events[2]["supersedes_event_id"] == second.value["event_id"]


def test_store_isolates_same_animal_id_between_users() -> None:
    _, store = _store()
    user_a = memory_namespace("user_a", "animal", "yak_032")
    user_b = memory_namespace("user_b", "animal", "yak_032")

    store.put(user_a, "profile", {"source": "user_confirmed", "nickname": "A"})
    store.put(user_b, "profile", {"source": "user_confirmed", "nickname": "B"})

    assert store.get(user_a, "profile").value["nickname"] == "A"  # type: ignore[union-attr]
    assert store.get(user_b, "profile").value["nickname"] == "B"  # type: ignore[union-attr]
    assert {item.value["nickname"] for item in store.search(("memory", "user_a"))} == {"A"}


def test_store_search_filters_query_limit_and_expired_records() -> None:
    now = [datetime(2026, 8, 28, tzinfo=UTC)]
    _, store = _store(clock=lambda: now[0])
    namespace = memory_namespace("user_a", "animal", "yak_032")
    store.put(
        namespace,
        "consultation_1",
        {"source": "user_confirmed", "memory_type": "consultation", "content": "calf diarrhea"},
        ttl=10,
    )
    now[0] += timedelta(minutes=1)
    store.put(
        namespace,
        "consultation_2",
        {"source": "user_confirmed", "memory_type": "consultation", "content": "reduced appetite"},
    )
    store.put(
        namespace,
        "profile",
        {"source": "tool_result", "memory_type": "profile", "content": "healthy yak"},
    )

    matches = store.search(
        namespace,
        query="appetite",
        filter={"memory_type": "consultation"},
        limit=1,
    )
    assert [item.key for item in matches] == ["consultation_2"]

    now[0] += timedelta(minutes=10)
    assert store.get(namespace, "consultation_1") is None
    assert {item.key for item in store.search(namespace)} == {"consultation_2", "profile"}


def test_store_rejects_untrusted_source_and_invalid_namespace() -> None:
    _, store = _store()
    namespace = memory_namespace("user_a", "animal", "yak_032")

    for invalid in (
        lambda: store.put(namespace, "diagnosis", {"source": "ai_inferred", "content": "x"}),
        lambda: store.put(("memory", "user_a"), "profile", {"source": "user_confirmed"}),
    ):
        try:
            invalid()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid memory write should be rejected")


def test_store_async_batch_and_namespace_listing() -> None:
    _, store = _store()
    namespace = memory_namespace("user_a", "farm", "farm_1")

    async def run() -> None:
        await store.aput(namespace, "profile", {"source": "tool_result", "location": "Qinghai"})
        item = await store.aget(namespace, "profile")
        assert item is not None and item.value["location"] == "Qinghai"

    asyncio.run(run())
    assert store.list_namespaces(prefix=("memory", "user_a")) == [namespace]
