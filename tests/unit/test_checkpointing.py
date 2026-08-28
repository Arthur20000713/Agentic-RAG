from __future__ import annotations

import asyncio
from operator import add
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.agent.checkpointing import (
    checkpoint_config,
    checkpoint_database_path,
    checkpoint_thread_id,
    open_sqlite_checkpointer,
)


class CheckpointState(TypedDict):
    history: Annotated[list[str], add]


def _build_graph(checkpointer):  # noqa: ANN001
    builder = StateGraph(CheckpointState)
    builder.add_node("record", lambda state: {})
    builder.add_edge(START, "record")
    builder.add_edge("record", END)
    return builder.compile(checkpointer=checkpointer)


def test_checkpoint_thread_id_is_tenant_scoped_and_unambiguous() -> None:
    assert checkpoint_thread_id("user_a", "session_1") != checkpoint_thread_id(
        "user_b", "session_1"
    )
    assert checkpoint_thread_id("a:b", "c") != checkpoint_thread_id("a", "b:c")


def test_checkpoint_thread_id_requires_both_identity_parts() -> None:
    for user_id, session_id in (("", "s1"), ("u1", ""), (" ", "s1")):
        try:
            checkpoint_thread_id(user_id, session_id)
        except ValueError as exc:
            assert "required" in str(exc)
        else:
            raise AssertionError("missing checkpoint identity should be rejected")


def test_checkpoint_database_path_is_separate_from_application_database() -> None:
    path = checkpoint_database_path("sqlite:///data/app.db")

    assert Path(path).name == "app.db.checkpoints.sqlite3"
    assert checkpoint_database_path("sqlite:///:memory:") == ":memory:"


def test_sqlite_checkpointer_restores_same_thread_and_isolates_other_threads(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "checkpoints.sqlite3"

    async def run() -> None:
        async with open_sqlite_checkpointer(checkpoint_path) as saver:
            graph = _build_graph(saver)
            first = await graph.ainvoke(
                {"history": ["first"]},
                config=checkpoint_config("user_a", "session_1"),
            )
            second = await graph.ainvoke(
                {"history": ["second"]},
                config=checkpoint_config("user_a", "session_1"),
            )
            isolated = await graph.ainvoke(
                {"history": ["other"]},
                config=checkpoint_config("user_b", "session_1"),
            )

        assert first["history"] == ["first"]
        assert second["history"] == ["first", "second"]
        assert isolated["history"] == ["other"]

    asyncio.run(run())


def test_sqlite_checkpointer_survives_connection_restart(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    config = checkpoint_config("user_a", "session_restart")

    async def run() -> None:
        async with open_sqlite_checkpointer(checkpoint_path) as saver:
            await _build_graph(saver).ainvoke({"history": ["before"]}, config=config)

        async with open_sqlite_checkpointer(checkpoint_path) as saver:
            result = await _build_graph(saver).ainvoke({"history": ["after"]}, config=config)

        assert result["history"] == ["before", "after"]

    asyncio.run(run())
