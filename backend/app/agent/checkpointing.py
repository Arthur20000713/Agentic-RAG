from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.app.core.config import PROJECT_ROOT


def checkpoint_thread_id(user_id: str, session_id: str) -> str:
    """Build an unambiguous tenant-scoped LangGraph thread ID."""

    owner = user_id.strip()
    session = session_id.strip()
    if not owner or not session:
        raise ValueError("user_id and session_id are required for checkpointing")
    return json.dumps([owner, session], ensure_ascii=False, separators=(",", ":"))


def checkpoint_config(user_id: str, session_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": checkpoint_thread_id(user_id, session_id)}}


def checkpoint_database_path(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("checkpointing requires a sqlite:/// database URL")
    value = database_url[len(prefix) :]
    if value == ":memory:":
        return value
    database_path = Path(value)
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    return str(database_path.with_suffix(database_path.suffix + ".checkpoints.sqlite3"))


@asynccontextmanager
async def open_sqlite_checkpointer(path: str | Path) -> AsyncIterator[AsyncSqliteSaver]:
    """Open and initialize a persistent async LangGraph checkpointer."""

    database_path = str(path)
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(database_path) as saver:
        await saver.setup()
        yield saver


__all__ = [
    "checkpoint_config",
    "checkpoint_database_path",
    "checkpoint_thread_id",
    "open_sqlite_checkpointer",
]
