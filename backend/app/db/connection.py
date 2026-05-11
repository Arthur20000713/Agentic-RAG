from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT


def _path_from_sqlite_url(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("only sqlite:/// database URLs are supported in V1")
    path = database_url[len(prefix) :]
    if path == ":memory:":
        return path
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return str(candidate)


def get_connection(database_url: str) -> sqlite3.Connection:
    path = _path_from_sqlite_url(database_url)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

