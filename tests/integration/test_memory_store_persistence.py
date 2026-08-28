from __future__ import annotations

from pathlib import Path

from backend.app.agent.memory_store import RepositoryMemoryStore, memory_namespace
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import MemoryRepository


def test_repository_store_survives_database_connection_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    namespace = memory_namespace("user_restart", "animal", "yak_032")

    first_connection = get_connection(database_url)
    init_db(first_connection)
    RepositoryMemoryStore(MemoryRepository(first_connection)).put(
        namespace,
        "profile",
        {"source": "tool_result", "species": "yak", "breed": "plateau"},
    )
    first_connection.close()

    second_connection = get_connection(database_url)
    init_db(second_connection)
    restored = RepositoryMemoryStore(MemoryRepository(second_connection)).get(namespace, "profile")
    second_connection.close()

    assert restored is not None
    assert restored.value["species"] == "yak"
    assert restored.value["breed"] == "plateau"
