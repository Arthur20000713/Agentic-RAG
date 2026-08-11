from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scripts import migrate_p4_sqlite_to_mysql as migration


mysql_connector = pytest.importorskip(
    "mysql.connector",
    reason="install the project migration extra to run MySQL migration tests",
)

MYSQL_IMAGE = "mysql:8.0.36"
MYSQL_ROOT_PASSWORD = "p4-isolated-root-password"
MYSQL_APP_USER = "p4_migration"
MYSQL_APP_PASSWORD = "p4-isolated-app-password"
MIGRATION_FILES = (
    "V1__platform_baseline.sql",
    "V2__iam_and_audit.sql",
    "V3__conversation_message_and_task.sql",
    "V4__legacy_import_ledger_and_maps.sql",
    "V5__message_request_id_is_correlation_only.sql",
)


@pytest.fixture(scope="module")
def isolated_mysql() -> Iterator[tuple[str, int]]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is unavailable")
    availability = subprocess.run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if availability.returncode != 0:
        pytest.skip("Docker daemon is unavailable")

    container_name = f"p4-migration-test-{uuid.uuid4().hex[:12]}"
    subprocess.run(
        [
            docker,
            "run",
            "--detach",
            "--rm",
            "--name",
            container_name,
            "--label",
            "livestock.test=p4-sqlite-migration",
            "--env",
            f"MYSQL_ROOT_PASSWORD={MYSQL_ROOT_PASSWORD}",
            "--env",
            "MYSQL_DATABASE=bootstrap",
            "--env",
            f"MYSQL_USER={MYSQL_APP_USER}",
            "--env",
            f"MYSQL_PASSWORD={MYSQL_APP_PASSWORD}",
            "--publish",
            "127.0.0.1::3306",
            MYSQL_IMAGE,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        port_result = subprocess.run(
            [docker, "port", container_name, "3306/tcp"],
            capture_output=True,
            text=True,
            check=True,
        )
        port = int(port_result.stdout.strip().rsplit(":", 1)[1])
        deadline = time.monotonic() + 60
        while True:
            try:
                connection = mysql_connector.connect(
                    host="127.0.0.1",
                    port=port,
                    user="root",
                    password=MYSQL_ROOT_PASSWORD,
                    connection_timeout=2,
                )
                connection.close()
                break
            except mysql_connector.Error:
                if time.monotonic() >= deadline:
                    raise AssertionError("isolated MySQL did not become ready")
                time.sleep(0.5)
        yield "127.0.0.1", port
    finally:
        subprocess.run(
            [docker, "rm", "--force", container_name],
            capture_output=True,
            text=True,
            check=False,
        )


def _create_source(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE conversation (
                session_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE qa_log (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                user_query TEXT NOT NULL,
                intent TEXT,
                tools_used TEXT,
                retrieved_chunks TEXT,
                final_answer TEXT,
                risk_level TEXT,
                latency_ms INTEGER,
                response_json TEXT,
                created_at TEXT
            );
            CREATE TABLE rag_ingestion_task (
                id INTEGER PRIMARY KEY,
                task_id TEXT UNIQUE NOT NULL
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO conversation (
                session_id, owner_id, title, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "legacy-session-1",
                    "legacy",
                    "Imported one",
                    "2026-07-10 08:00:00",
                    "2026-07-10 08:01:00",
                ),
                (
                    "legacy-session-2",
                    "untrusted-client",
                    "Imported two",
                    "2026-07-11 09:00:00",
                    "2026-07-11 09:02:00",
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO qa_log (
                id, session_id, user_query, intent, tools_used,
                retrieved_chunks, final_answer, risk_level, latency_ms,
                response_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    11,
                    "legacy-session-1",
                    "How should calves be monitored?",
                    "general_qa",
                    '["livestock_rag_search"]',
                    '[{"chunk_id":"chunk-1"}]',
                    "Monitor appetite, hydration, manure and attitude.",
                    "LOW",
                    15,
                    '{"errors":[],"answer":"ok"}',
                    "2026-07-10 08:01:00",
                ),
                (
                    12,
                    "legacy-session-2",
                    "What records should a farm retain?",
                    "general_qa",
                    "[]",
                    "[]",
                    "Retain animal, health, feeding and treatment records.",
                    None,
                    8,
                    None,
                    "2026-07-11 09:02:00",
                ),
            ],
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _root_connection(host: str, port: int, database: str | None = None) -> Any:
    return mysql_connector.connect(
        host=host,
        port=port,
        user="root",
        password=MYSQL_ROOT_PASSWORD,
        database=database,
        autocommit=True,
        charset="utf8mb4",
    )


def _app_connection(host: str, port: int, database: str) -> Any:
    return mysql_connector.connect(
        host=host,
        port=port,
        user=MYSQL_APP_USER,
        password=MYSQL_APP_PASSWORD,
        database=database,
        autocommit=True,
        charset="utf8mb4",
    )


def _prepare_database(host: str, port: int, database: str) -> None:
    with _root_connection(host, port) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"CREATE DATABASE `{database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
        cursor.execute(
            f"GRANT ALL PRIVILEGES ON `{database}`.* "
            f"TO '{MYSQL_APP_USER}'@'%'"
        )
        cursor.close()

    migration_directory = (
        Path(__file__).parents[2]
        / "java-app"
        / "src"
        / "main"
        / "resources"
        / "db"
        / "migration"
    )
    with _app_connection(host, port, database) as connection:
        cursor = connection.cursor()
        for filename in MIGRATION_FILES:
            sql = (migration_directory / filename).read_text(encoding="utf-8")
            for statement in sql.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        cursor.close()


class _CorruptingCursor:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.corrupted = False

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        normalized = " ".join(sql.split())
        if (
            not self.corrupted
            and "FROM legacy_import_id_map" in normalized
            and "entity_type = 'AI_QUERY_TASK'" in normalized
            and normalized.startswith("SELECT COUNT(*)")
        ):
            ledger_id = parameters[0]
            self._inner.execute(
                """
                UPDATE legacy_import_id_map
                SET target_id = 9223372036854770000
                WHERE run_id = %s
                  AND entity_type = 'AI_QUERY_TASK'
                LIMIT 1
                """,
                (ledger_id,),
            )
            assert self._inner.rowcount == 1
            self.corrupted = True
        return self._inner.execute(sql, parameters)

    def fetchone(self) -> Any:
        return self._inner.fetchone()

    def fetchall(self) -> Any:
        return self._inner.fetchall()

    @property
    def lastrowid(self) -> Any:
        return self._inner.lastrowid

    @property
    def rowcount(self) -> Any:
        return self._inner.rowcount

    def close(self) -> None:
        self._inner.close()


class _CorruptingConnection:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.cursor_wrapper: _CorruptingCursor | None = None
        self.rollback_called = False

    def cursor(self) -> _CorruptingCursor:
        self.cursor_wrapper = _CorruptingCursor(self._inner.cursor())
        return self.cursor_wrapper

    def start_transaction(self) -> None:
        self._inner.start_transaction()

    def commit(self) -> None:
        self._inner.commit()

    def rollback(self) -> None:
        self.rollback_called = True
        self._inner.rollback()

    def close(self) -> None:
        self._inner.close()


def _count(connection: Any, table: str) -> int:
    cursor = connection.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
    value = int(cursor.fetchone()[0])
    cursor.close()
    return value


def test_apply_and_corrupted_task_map_rollback_use_isolated_mysql(
    isolated_mysql: tuple[str, int],
    tmp_path: Path,
) -> None:
    host, port = isolated_mysql
    source = tmp_path / "legacy.db"
    backup = tmp_path / "legacy.backup.db"
    _create_source(source)
    shutil.copyfile(source, backup)
    source_hash = _sha256(source)
    plan = migration.build_import_plan(source, source_hash)

    success_database = "p4_migration_success"
    _prepare_database(host, port, success_database)
    success_connection = _app_connection(host, port, success_database)
    try:
        report = migration.apply_import(
            plan,
            backup,
            source_hash,
            success_connection,
            lock_timeout_seconds=5,
        )
    finally:
        success_connection.close()

    assert report["status"] == "succeeded"
    assert report["importedCounts"] == {
        "shadowUsers": 2,
        "conversations": 2,
        "messages": 4,
        "tasks": 2,
        "idMaps": 8,
    }
    with _app_connection(host, port, success_database) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT im.source_id, im.target_id, t.id, t.conversation_id,
                   t.operation_id, t.request_hash, t.result_ref,
                   m.id, m.role
            FROM legacy_import_id_map im
            JOIN biz_task t ON t.id = im.target_id
            JOIN conversation_message m
              ON t.result_ref = CAST(m.id AS CHAR)
            WHERE im.entity_type = 'AI_QUERY_TASK'
            ORDER BY CAST(im.source_id AS UNSIGNED)
            """
        )
        persisted_maps = cursor.fetchall()
        assert len(persisted_maps) == len(plan.qa_rows)
        qa_by_id = {str(item.source_id): item for item in plan.qa_rows}
        for (
            source_id,
            mapped_target_id,
            task_id,
            conversation_id,
            operation_id,
            request_hash,
            result_ref,
            message_id,
            role,
        ) in persisted_maps:
            item = qa_by_id[str(source_id)]
            assert int(mapped_target_id) == int(task_id)
            assert operation_id == item.operation_id
            assert request_hash == migration.java_request_hash(
                conversation_id=int(conversation_id),
                context_version=0,
                user_query=item.user_query,
            )
            assert str(result_ref) == str(message_id)
            assert role == "ASSISTANT"
        cursor.execute(
            "SELECT status FROM legacy_import_run WHERE run_id = %s",
            (report["runId"],),
        )
        assert cursor.fetchone()[0] == "SUCCEEDED"
        cursor.close()

    rollback_database = "p4_migration_rollback"
    _prepare_database(host, port, rollback_database)
    wrapped = _CorruptingConnection(
        _app_connection(host, port, rollback_database)
    )
    try:
        with pytest.raises(
            migration.MigrationError,
            match="AI task map reconciliation failed",
        ):
            migration.apply_import(
                plan,
                backup,
                source_hash,
                wrapped,
                lock_timeout_seconds=5,
            )
        assert wrapped.rollback_called is True
        assert wrapped.cursor_wrapper is not None
        assert wrapped.cursor_wrapper.corrupted is True
    finally:
        wrapped.close()

    with _app_connection(host, port, rollback_database) as connection:
        for table in (
            "conversation",
            "conversation_message",
            "biz_task",
            "legacy_import_run",
            "legacy_import_owner_map",
            "legacy_import_id_map",
            "audit_log",
        ):
            assert _count(connection, table) == 0
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sys_user WHERE username LIKE 'legacy_import_%'"
        )
        assert int(cursor.fetchone()[0]) == 0
        cursor.close()

    assert _sha256(source) == source_hash
    assert _sha256(backup) == source_hash
