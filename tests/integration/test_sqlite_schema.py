from __future__ import annotations

from backend.app.db.connection import get_connection
from backend.app.db.migrations import APPLICATION_TABLES, init_db


def test_init_db_creates_only_application_tables() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    table_names = {row["name"] for row in rows}

    assert APPLICATION_TABLES.issubset(table_names)
    assert "chunk" not in table_names
    assert "vector_index" not in table_names

