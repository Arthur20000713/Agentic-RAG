from __future__ import annotations

from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db


def test_session_context_schema_matches_contract() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)

    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(session_context)").fetchall()
    }
    indexes = conn.execute("PRAGMA index_list(session_context)").fetchall()

    assert set(columns) == {"id", "session_id", "context_json", "expires_at", "status", "updated_at"}
    assert columns["session_id"]["notnull"] == 1
    assert columns["context_json"]["notnull"] == 1
    assert columns["status"]["dflt_value"] == "'active'"
    assert any(row["unique"] == 1 for row in indexes)
