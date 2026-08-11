from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from scripts import migrate_p4_sqlite_to_mysql as migration


def _create_source(path: Path, *, ingestion_rows: int = 0) -> None:
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
                    "session-a",
                    "legacy",
                    "First",
                    "2026-07-10 08:00:00",
                    "2026-07-10 08:01:00",
                ),
                (
                    "session-b",
                    "client-untrusted",
                    "Second",
                    "2026-07-11T09:00:00Z",
                    "2026-07-11T09:02:00Z",
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
                    1,
                    "session-a",
                    "Question",
                    "general_qa",
                    '["rag"]',
                    "[]",
                    "Answer",
                    "low",
                    12,
                    "{}",
                    "2026-07-10 08:01:00",
                ),
                (
                    2,
                    "session-b",
                    "Another question",
                    "general_qa",
                    '["rag", "verifier"]',
                    '[{"id": "chunk"}]',
                    "Another answer",
                    None,
                    20,
                    None,
                    "2026-07-11T09:02:00Z",
                ),
            ],
        )
        if ingestion_rows:
            connection.execute(
                "INSERT INTO rag_ingestion_task (id, task_id) VALUES (1, 'task-1')"
            )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dry_run_builds_two_messages_per_qa_without_mutating_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source)
    before_hash = _sha256(source)
    before_mtime = source.stat().st_mtime_ns

    plan = migration.build_import_plan(source, before_hash)
    report = migration.dry_run_report(plan, None)

    assert plan.expected_counts == {
        "shadowUsers": 2,
        "conversations": 2,
        "messages": 4,
        "tasks": 2,
        "idMaps": 8,
    }
    assert plan.qa_rows[0].risk_level == "LOW"
    assert plan.qa_rows[0].retrieved_chunk_count == 0
    assert plan.qa_rows[1].retrieved_chunk_count == 1
    assert plan.qa_rows[0].operation_id.startswith("legacy-p4-")
    assert len(plan.qa_rows[0].source_projection_hash) == 64
    assert report["mode"] == "dry-run"
    assert report["checks"]["ragIngestionTaskEmpty"] is True
    assert _sha256(source) == before_hash
    assert source.stat().st_mtime_ns == before_mtime


def test_preflight_rejects_wrong_expected_sha256(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source)

    with pytest.raises(migration.MigrationError, match="does not match"):
        migration.build_import_plan(source, "0" * 64)


def test_preflight_rejects_nonempty_rag_ingestion_task(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source, ingestion_rows=1)

    with pytest.raises(migration.MigrationError, match="rag_ingestion_task"):
        migration.build_import_plan(source, _sha256(source))


def test_preflight_rejects_error_response_instead_of_creating_success_task(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source)
    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            UPDATE qa_log
            SET response_json = '{"errors":[{"code":"MODEL_FAILED"}]}'
            WHERE id = 1
            """
        )

    with pytest.raises(migration.MigrationError, match="indicates an error"):
        migration.build_import_plan(source, _sha256(source))


def test_preflight_rejects_blank_answer_instead_of_creating_success_task(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source)
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE qa_log SET final_answer = ' ' WHERE id = 1")

    with pytest.raises(migration.MigrationError, match="split into two messages"):
        migration.build_import_plan(source, _sha256(source))


def test_canonical_source_projection_hash_is_stable_and_sensitive() -> None:
    baseline = migration.canonical_source_projection_hash(
        source_id=7,
        session_id="session-一",
        user_query="犊牛腹泻怎么办？",
    )

    assert baseline == migration.canonical_source_projection_hash(
        source_id=7,
        session_id="session-一",
        user_query="犊牛腹泻怎么办？",
    )
    assert baseline != migration.canonical_source_projection_hash(
        source_id=7,
        session_id="session-一",
        user_query="不同问题",
    )
    assert len(baseline) == 64


def test_java_request_hash_matches_java_idempotency_hasher_vector() -> None:
    assert migration.java_request_hash(
        conversation_id=42,
        context_version=3,
        user_query="same content",
    ) == "d8595d81e94dc1b97f4f60284696dcc487fb01e4238c046230a8f064534c6250"


def test_full_persisted_task_map_projection_rejects_missing_or_wrong_rows() -> None:
    expected = {
        "1": ("legacy-operation-1", "a" * 64),
        "2": ("legacy-operation-2", "b" * 64),
    }
    migration.validate_task_map_projection(
        [
            ("1", "legacy-operation-1", "a" * 64),
            ("2", "legacy-operation-2", "b" * 64),
        ],
        expected,
    )

    with pytest.raises(migration.MigrationError, match="projection reconciliation"):
        migration.validate_task_map_projection(
            [("1", "legacy-operation-1", "a" * 64)],
            expected,
        )
    with pytest.raises(migration.MigrationError, match="projection reconciliation"):
        migration.validate_task_map_projection(
            [
                ("1", "legacy-operation-1", "a" * 64),
                ("2", "legacy-operation-2", "c" * 64),
            ],
            expected,
        )


def test_preflight_rejects_nonempty_sqlite_wal_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source)
    source.with_name(source.name + "-wal").write_bytes(b"uncheckpointed")

    with pytest.raises(migration.MigrationError, match="not quiescent"):
        migration.build_import_plan(source, _sha256(source))


def test_apply_requires_distinct_matching_backup(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    backup = tmp_path / "legacy.backup.db"
    _create_source(source)
    source_hash = _sha256(source)

    with pytest.raises(migration.MigrationError, match="required"):
        migration._verify_backup(source, None, source_hash, True)
    with pytest.raises(migration.MigrationError, match="distinct"):
        migration._verify_backup(source, source, source_hash, True)

    shutil.copyfile(source, backup)
    assert migration._verify_backup(source, backup, source_hash, True) == source_hash


def test_apply_rejects_hard_link_as_backup(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    hard_link = tmp_path / "legacy-hard-link.db"
    _create_source(source)
    try:
        os.link(source, hard_link)
    except OSError as exc:
        pytest.skip(f"filesystem does not support hard links: {exc}")

    with pytest.raises(migration.MigrationError, match="distinct"):
        migration._verify_backup(source, hard_link, _sha256(source), True)


def test_apply_rejects_backup_with_nonempty_wal_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    backup = tmp_path / "legacy.backup.db"
    _create_source(source)
    shutil.copyfile(source, backup)
    backup.with_name(backup.name + "-wal").write_bytes(b"uncheckpointed")

    with pytest.raises(migration.MigrationError, match="SQLite backup is not quiescent"):
        migration._verify_backup(source, backup, _sha256(source), True)


def test_last_message_uses_parsed_utc_instead_of_text_order(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source)
    with sqlite3.connect(source) as connection:
        connection.execute(
            """
            UPDATE qa_log
            SET created_at = '2026-07-10T10:00:00+08:00'
            WHERE id = 1
            """
        )
        connection.execute(
            """
            INSERT INTO qa_log (
                id, session_id, user_query, intent, tools_used,
                retrieved_chunks, final_answer, risk_level, latency_ms,
                response_json, created_at
            )
            VALUES (
                3, 'session-a', 'Later UTC', 'general_qa', '[]',
                '[]', 'Later answer', NULL, 1, NULL,
                '2026-07-10 03:00:00'
            )
            """
        )

    plan = migration.build_import_plan(source, _sha256(source))
    conversation = next(
        item for item in plan.conversations if item.session_id == "session-a"
    )

    assert conversation.last_message_at == datetime(2026, 7, 10, 3, 0, 0)


def test_explicit_dry_run_cli_does_not_require_mysql(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "legacy.db"
    _create_source(source)

    exit_code = migration.main(
        [
            "--source",
            str(source),
            "--expected-sha256",
            _sha256(source),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert '"mode": "dry-run"' in capsys.readouterr().out


class _NonEmptyTargetCursor:
    def __init__(self) -> None:
        self._row = (0,)
        self.released = False

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> None:
        normalized = " ".join(sql.split())
        if "GET_LOCK" in normalized:
            self._row = (1,)
        elif normalized == "SET time_zone = '+00:00'":
            self._row = (0,)
        elif normalized == "SELECT @@session.time_zone":
            self._row = ("+00:00",)
        elif "information_schema.tables" in normalized:
            self._row = (3,)
        elif "COUNT(*) FROM `conversation`" in normalized:
            self._row = (1,)
        elif "COUNT(*) FROM `conversation_message`" in normalized:
            self._row = (0,)
        elif "COUNT(*) FROM `biz_task`" in normalized:
            self._row = (0,)
        elif "RELEASE_LOCK" in normalized:
            self.released = True
            self._row = (1,)
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self) -> tuple[int]:
        return self._row

    def close(self) -> None:
        pass


class _NonEmptyTargetConnection:
    def __init__(self) -> None:
        self.cursor_instance = _NonEmptyTargetCursor()
        self.rollback_called = False
        self.transaction_started = False

    def cursor(self) -> _NonEmptyTargetCursor:
        return self.cursor_instance

    def rollback(self) -> None:
        self.rollback_called = True

    def start_transaction(self) -> None:
        self.transaction_started = True


def test_apply_refuses_nonempty_target_before_starting_transaction(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    backup = tmp_path / "legacy.backup.db"
    _create_source(source)
    shutil.copyfile(source, backup)
    plan = migration.build_import_plan(source, _sha256(source))
    connection = _NonEmptyTargetConnection()

    with pytest.raises(migration.MigrationError, match="not empty"):
        migration.apply_import(
            plan,
            backup,
            plan.source_sha256,
            connection,
            lock_timeout_seconds=0,
        )

    assert connection.transaction_started is False
    assert connection.cursor_instance.released is True
