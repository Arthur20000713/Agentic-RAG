from __future__ import annotations

from backend.app.db.connection import get_connection
from backend.app.db.migrations import APPLICATION_TABLES, init_db


def test_memory_event_schema_is_append_only_contract() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(memory_event)").fetchall()
    }
    indexes = conn.execute("PRAGMA index_list(memory_event)").fetchall()

    assert "memory_event" in APPLICATION_TABLES
    assert set(columns) == {
        "id",
        "event_id",
        "subject_type",
        "subject_id",
        "event_type",
        "source",
        "payload_json",
        "supersedes_event_id",
        "status",
        "created_at",
    }
    assert columns["event_id"]["notnull"] == 1
    assert columns["subject_type"]["notnull"] == 1
    assert columns["subject_id"]["notnull"] == 1
    assert columns["payload_json"]["notnull"] == 1
    assert columns["status"]["dflt_value"] == "'active'"
    assert any(row["unique"] == 1 for row in indexes)
