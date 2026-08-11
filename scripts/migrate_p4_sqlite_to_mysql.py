"""Offline P4 conversation migration from legacy SQLite to MySQL.

The command is dry-run by default. Applying the migration requires an exact
source SHA256, an independently created byte-for-byte backup, MySQL credentials
from environment variables, an empty P4 target domain, and an explicit
``--apply`` flag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import struct
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DOMAIN = "P4_CONVERSATION"
LOCK_NAME = "livestock:p4:sqlite-import"
REQUIRED_SQLITE_COLUMNS = {
    "conversation": {
        "session_id",
        "owner_id",
        "title",
        "created_at",
        "updated_at",
    },
    "qa_log": {
        "id",
        "session_id",
        "user_query",
        "intent",
        "tools_used",
        "retrieved_chunks",
        "final_answer",
        "risk_level",
        "latency_ms",
        "response_json",
        "created_at",
    },
    "rag_ingestion_task": {"id", "task_id"},
}
TARGET_TABLES = ("conversation", "conversation_message", "biz_task")
IMPORT_TABLES = (
    "legacy_import_run",
    "legacy_import_owner_map",
    "legacy_import_id_map",
)
VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


class MigrationError(RuntimeError):
    """Safe, user-facing migration failure."""


@dataclass(frozen=True)
class LegacyConversation:
    session_id: str
    owner_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True)
class LegacyQa:
    source_id: int
    session_id: str
    user_query: str
    final_answer: str
    intent: str | None
    risk_level: str | None
    created_at: datetime
    latency_ms: int | None
    tool_names: tuple[str, ...]
    retrieved_chunk_count: int | None
    response_present: bool
    operation_id: str
    source_projection_hash: str


@dataclass(frozen=True)
class ImportPlan:
    source_path: Path
    source_sha256: str
    source_size_bytes: int
    conversations: tuple[LegacyConversation, ...]
    qa_rows: tuple[LegacyQa, ...]
    owners: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def expected_counts(self) -> dict[str, int]:
        return {
            "shadowUsers": len(self.owners),
            "conversations": len(self.conversations),
            "messages": len(self.qa_rows) * 2,
            "tasks": len(self.qa_rows),
            "idMaps": len(self.conversations) + len(self.qa_rows) * 3,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise MigrationError("expected SHA256 must contain exactly 64 hexadecimal characters")
    return normalized


def parse_legacy_time(value: Any, *, field: str) -> datetime:
    if value is None or not str(value).strip():
        raise MigrationError(f"{field} must contain a timestamp")
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise MigrationError(f"{field} contains an invalid timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _read_json_list(value: Any) -> tuple[list[Any] | None, bool]:
    if value is None or not str(value).strip():
        return [], True
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return None, False
    if not isinstance(parsed, list):
        return None, False
    return parsed, True


def canonical_source_projection_hash(
    *,
    source_id: int,
    session_id: str,
    user_query: str,
) -> str:
    # Legacy rows have no trustworthy Java contextVersion or target conversation ID.
    # This import-provenance hash is deliberately not a live replay hash.
    projection = {
        "operationType": "AI_QUERY",
        "qaLogId": source_id,
        "sessionId": session_id,
        "userQuery": user_query,
    }
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def java_request_hash(
    *,
    conversation_id: int,
    context_version: int,
    user_query: str,
) -> str:
    """Mirror Java IdempotencyHasher.requestHash byte-for-byte."""

    digest = hashlib.sha256()
    digest.update(struct.pack(">q", conversation_id))
    for text in ("AI_QUERY",):
        encoded = text.encode("utf-8")
        digest.update(struct.pack(">i", len(encoded)))
        digest.update(encoded)
    digest.update(struct.pack(">q", context_version))
    encoded_query = user_query.encode("utf-8")
    digest.update(struct.pack(">i", len(encoded_query)))
    digest.update(encoded_query)
    return digest.hexdigest()


def _response_indicates_error(value: Any) -> bool:
    if not isinstance(value, dict):
        return True
    for key in (
        "error",
        "errors",
        "error_code",
        "errorCode",
        "error_message",
        "errorMessage",
    ):
        candidate = value.get(key)
        if isinstance(candidate, bool) and candidate:
            return True
        if isinstance(candidate, (str, list, dict)) and bool(candidate):
            return True
        if isinstance(candidate, (int, float)) and candidate != 0:
            return True
    if value.get("success") is False or value.get("ok") is False:
        return True
    if value.get("isError") is True:
        return True
    status = str(value.get("status", "")).strip().lower()
    return status in {
        "error",
        "failed",
        "failure",
        "timed_out",
        "timeout",
        "cancelled",
        "canceled",
    }


def _sqlite_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro&immutable=1"


def _ensure_quiescent_source(path: Path, *, label: str = "SQLite source") -> None:
    for suffix in ("-wal", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() and sidecar.stat().st_size > 0:
            raise MigrationError(
                f"{label} is not quiescent: non-empty {sidecar.name} exists"
            )


def _validate_sqlite_schema(connection: sqlite3.Connection) -> None:
    integrity = [str(row[0]).lower() for row in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise MigrationError("SQLite integrity_check did not return ok")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise MigrationError("SQLite foreign_key_check found violations")

    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing_tables = sorted(REQUIRED_SQLITE_COLUMNS.keys() - tables)
    if missing_tables:
        raise MigrationError(f"SQLite schema is missing tables: {', '.join(missing_tables)}")
    for table, required in REQUIRED_SQLITE_COLUMNS.items():
        columns = {
            str(row[1])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        }
        missing = sorted(required - columns)
        if missing:
            raise MigrationError(
                f"SQLite table {table} is missing columns: {', '.join(missing)}"
            )


def build_import_plan(source: Path, expected_sha256: str) -> ImportPlan:
    source = source.resolve()
    if not source.is_file():
        raise MigrationError("SQLite source does not exist or is not a regular file")
    _ensure_quiescent_source(source)
    expected = normalize_sha256(expected_sha256)
    initial_hash = sha256_file(source)
    if initial_hash != expected:
        raise MigrationError("SQLite source SHA256 does not match --expected-sha256")

    warnings: list[str] = []
    with sqlite3.connect(_sqlite_uri(source), uri=True) as connection:
        connection.row_factory = sqlite3.Row
        _validate_sqlite_schema(connection)

        ingestion_count = int(
            connection.execute("SELECT COUNT(*) FROM rag_ingestion_task").fetchone()[0]
        )
        if ingestion_count:
            raise MigrationError(
                "rag_ingestion_task is non-empty; P4 cannot safely import knowledge tasks"
            )

        orphan_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM qa_log AS q
                LEFT JOIN conversation AS c ON c.session_id = q.session_id
                WHERE q.session_id IS NULL
                   OR TRIM(q.session_id) = ''
                   OR c.session_id IS NULL
                """
            ).fetchone()[0]
        )
        if orphan_count:
            raise MigrationError("qa_log contains rows without a valid conversation")

        last_messages: dict[str, datetime] = {}
        for row in connection.execute(
            "SELECT id, session_id, created_at FROM qa_log ORDER BY id"
        ):
            parsed = parse_legacy_time(
                row["created_at"],
                field=f"qa_log {row['id']} created_at",
            )
            session_id = str(row["session_id"])
            current = last_messages.get(session_id)
            if current is None or parsed > current:
                last_messages[session_id] = parsed

        conversations: list[LegacyConversation] = []
        for row in connection.execute(
            """
            SELECT session_id, owner_id, title, created_at, updated_at
            FROM conversation
            ORDER BY session_id
            """
        ):
            session_id = str(row["session_id"] or "")
            owner_id = str(row["owner_id"] or "")
            title = str(row["title"] or "")
            if not session_id.strip() or len(session_id) > 255:
                raise MigrationError("conversation contains an invalid session_id")
            if not owner_id.strip() or len(owner_id) > 255:
                raise MigrationError(f"conversation {session_id} has an invalid owner_id")
            if not title.strip() or len(title) > 255:
                raise MigrationError(f"conversation {session_id} has an invalid title")
            conversations.append(
                LegacyConversation(
                    session_id=session_id,
                    owner_id=owner_id,
                    title=title,
                    created_at=parse_legacy_time(
                        row["created_at"],
                        field=f"conversation {session_id} created_at",
                    ),
                    updated_at=parse_legacy_time(
                        row["updated_at"],
                        field=f"conversation {session_id} updated_at",
                    ),
                    last_message_at=last_messages.get(session_id),
                )
            )

        qa_rows: list[LegacyQa] = []
        for row in connection.execute(
            """
            SELECT id, session_id, user_query, intent, tools_used,
                   retrieved_chunks, final_answer, risk_level, latency_ms,
                   response_json, created_at
            FROM qa_log
            ORDER BY id
            """
        ):
            source_id = int(row["id"])
            user_query = str(row["user_query"] or "")
            final_answer = str(row["final_answer"] or "")
            if not user_query.strip() or not final_answer.strip():
                raise MigrationError(f"qa_log {source_id} cannot be split into two messages")
            intent = None if row["intent"] is None else str(row["intent"])
            if intent is not None and len(intent) > 128:
                raise MigrationError(f"qa_log {source_id} intent exceeds 128 characters")
            raw_risk = (
                None
                if row["risk_level"] is None
                else str(row["risk_level"]).strip().upper()
            )
            risk = raw_risk if raw_risk in VALID_RISK_LEVELS else None
            if raw_risk and risk is None:
                warnings.append(f"qa_log {source_id}: unsupported risk_level omitted")

            tools, tools_valid = _read_json_list(row["tools_used"])
            if not tools_valid:
                warnings.append(f"qa_log {source_id}: invalid tools_used JSON summarized")
            tool_names = tuple(str(item) for item in (tools or []) if isinstance(item, str))

            chunks, chunks_valid = _read_json_list(row["retrieved_chunks"])
            if not chunks_valid:
                warnings.append(f"qa_log {source_id}: invalid retrieved_chunks JSON summarized")
            response_present = bool(
                row["response_json"] is not None
                and str(row["response_json"]).strip()
            )
            if response_present:
                try:
                    response = json.loads(str(row["response_json"]))
                except json.JSONDecodeError as exc:
                    raise MigrationError(
                        f"qa_log {source_id} response_json is invalid"
                    ) from exc
                if _response_indicates_error(response):
                    raise MigrationError(
                        f"qa_log {source_id} response_json indicates an error"
                    )
            operation_id = f"legacy-p4-{initial_hash[:16]}-qa-{source_id}"
            qa_rows.append(
                LegacyQa(
                    source_id=source_id,
                    session_id=str(row["session_id"]),
                    user_query=user_query,
                    final_answer=final_answer,
                    intent=intent,
                    risk_level=risk,
                    created_at=parse_legacy_time(
                        row["created_at"],
                        field=f"qa_log {source_id} created_at",
                    ),
                    latency_ms=(
                        None if row["latency_ms"] is None else int(row["latency_ms"])
                    ),
                    tool_names=tool_names,
                    retrieved_chunk_count=None if chunks is None else len(chunks),
                    response_present=response_present,
                    operation_id=operation_id,
                    source_projection_hash=canonical_source_projection_hash(
                        source_id=source_id,
                        session_id=str(row["session_id"]),
                        user_query=user_query,
                    ),
                )
            )

    _ensure_quiescent_source(source)
    final_hash = sha256_file(source)
    if final_hash != initial_hash:
        raise MigrationError("SQLite source changed while it was being read")

    known_sessions = {item.session_id for item in conversations}
    if len(known_sessions) != len(conversations):
        raise MigrationError("conversation contains duplicate session IDs")
    if len({item.source_id for item in qa_rows}) != len(qa_rows):
        raise MigrationError("qa_log contains duplicate source IDs")
    if any(item.session_id not in known_sessions for item in qa_rows):
        raise MigrationError("qa_log contains an unknown session ID")

    return ImportPlan(
        source_path=source,
        source_sha256=initial_hash,
        source_size_bytes=source.stat().st_size,
        conversations=tuple(conversations),
        qa_rows=tuple(qa_rows),
        owners=tuple(sorted({item.owner_id for item in conversations})),
        warnings=tuple(warnings),
    )


def dry_run_report(plan: ImportPlan, backup_sha256: str | None) -> dict[str, Any]:
    timestamps = [
        item.created_at for item in plan.conversations
    ] + [item.created_at for item in plan.qa_rows]
    return {
        "mode": "dry-run",
        "domain": DOMAIN,
        "source": {
            "name": plan.source_path.name,
            "sha256": plan.source_sha256,
            "sizeBytes": plan.source_size_bytes,
            "backupSha256": backup_sha256,
            "integrity": "ok",
            "schema": "ok",
            "quiescent": True,
        },
        "expectedCounts": plan.expected_counts,
        "sourceTimeRangeUtc": {
            "min": min(timestamps).isoformat(timespec="microseconds") + "Z",
            "max": max(timestamps).isoformat(timespec="microseconds") + "Z",
        }
        if timestamps
        else None,
        "ownerMapping": {
            "strategy": "one disabled shadow user per untrusted legacy owner",
            "sourceOwnerDigests": [
                hashlib.sha256(owner.encode("utf-8")).hexdigest()
                for owner in plan.owners
            ],
        },
        "warnings": list(plan.warnings),
        "checks": {
            "ragIngestionTaskEmpty": True,
            "qaConversationForeignKeys": "ok",
            "messageSplit": "two messages per qa_log row",
            "historicalAiTasks": (
                "one SUCCEEDED AI_QUERY task per validated qa_log row"
            ),
            "taskIdentity": "operation_id equals both message turn_id values",
            "taskRequestHash": (
                "Java IdempotencyHasher byte protocol with mapped conversation ID "
                "and contextVersion 0"
            ),
            "sourceProjectionHash": (
                "canonical legacy request projection SHA256 retained in message metadata"
            ),
            "historicalReplay": (
                "hash semantics match Java; disabled shadow owners keep imports isolated"
            ),
            "targetDomainEmpty": "checked only during --apply",
            "mysqlLockAndTransaction": "used only during --apply",
        },
    }


def _mysql_settings_from_environment() -> dict[str, Any]:
    required = ("MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise MigrationError(
            "missing MySQL environment variables: " + ", ".join(missing)
        )
    try:
        port = int(os.environ.get("MYSQL_PORT", "3306"))
    except ValueError as exc:
        raise MigrationError("MYSQL_PORT must be an integer") from exc
    return {
        "host": os.environ["MYSQL_HOST"],
        "port": port,
        "database": os.environ["MYSQL_DATABASE"],
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
    }


def connect_mysql() -> Any:
    settings = _mysql_settings_from_environment()
    try:
        import mysql.connector  # type: ignore[import-not-found]

        return mysql.connector.connect(
            **settings,
            autocommit=True,
            connection_timeout=10,
            charset="utf8mb4",
        )
    except ImportError:
        pass
    try:
        import pymysql  # type: ignore[import-not-found]

        return pymysql.connect(
            **settings,
            autocommit=True,
            connect_timeout=10,
            charset="utf8mb4",
        )
    except ImportError as exc:
        raise MigrationError(
            "install mysql-connector-python or PyMySQL before using --apply"
        ) from exc


def _fetch_scalar(cursor: Any, sql: str, parameters: Iterable[Any] = ()) -> int:
    cursor.execute(sql, tuple(parameters))
    row = cursor.fetchone()
    return int(row[0])


def _start_transaction(connection: Any) -> None:
    if hasattr(connection, "start_transaction"):
        connection.start_transaction()
    else:
        connection.begin()


def _shadow_username(run_id: str, owner_id: str) -> str:
    owner_digest = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()
    return f"legacy_import_{run_id.replace('-', '')[:16]}_{owner_digest[:24]}"


def _message_fingerprint(
    role: str,
    content: str,
    intent: str | None,
    risk_level: str | None,
) -> str:
    payload = json.dumps(
        [role, content, intent, risk_level],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sample_source_ids(rows: tuple[LegacyQa, ...]) -> list[int]:
    if not rows:
        return []
    indexes = sorted({0, len(rows) // 2, len(rows) - 1})
    return [rows[index].source_id for index in indexes]


def validate_task_map_projection(
    persisted_rows: Iterable[tuple[Any, Any, Any]],
    expected: dict[str, tuple[str, str]],
) -> None:
    rows = list(persisted_rows)
    actual = {
        str(source_id): (str(operation_id), str(request_hash))
        for source_id, operation_id, request_hash in rows
    }
    if len(rows) != len(expected) or actual != expected:
        raise MigrationError("post-import AI task projection reconciliation failed")


def _source_time_range(plan: ImportPlan) -> tuple[datetime, datetime] | None:
    timestamps = [
        item.created_at for item in plan.conversations
    ] + [item.created_at for item in plan.qa_rows]
    if not timestamps:
        return None
    return min(timestamps), max(timestamps)


def apply_import(
    plan: ImportPlan,
    backup_path: Path,
    backup_sha256: str,
    connection: Any,
    *,
    lock_timeout_seconds: int,
) -> dict[str, Any]:
    run_uuid = str(uuid.uuid4())
    cursor = connection.cursor()
    acquired = False
    try:
        _ensure_quiescent_source(plan.source_path)
        if sha256_file(plan.source_path) != plan.source_sha256:
            raise MigrationError("SQLite source changed before the MySQL transaction")
        if os.path.samefile(plan.source_path, backup_path):
            raise MigrationError("backup is not independent from the SQLite source")
        _ensure_quiescent_source(backup_path, label="SQLite backup")
        if sha256_file(backup_path) != backup_sha256:
            raise MigrationError("backup changed before the MySQL transaction")

        acquired = (
            _fetch_scalar(
                cursor,
                "SELECT GET_LOCK(%s, %s)",
                (LOCK_NAME, lock_timeout_seconds),
            )
            == 1
        )
        if not acquired:
            raise MigrationError("could not acquire the P4 migration lock")
        cursor.execute("SET time_zone = '+00:00'")
        cursor.execute("SELECT @@session.time_zone")
        if str(cursor.fetchone()[0]) != "+00:00":
            raise MigrationError("could not force the MySQL session time zone to UTC")

        import_table_count = _fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name IN (%s, %s, %s)
            """,
            IMPORT_TABLES,
        )
        if import_table_count != len(IMPORT_TABLES):
            raise MigrationError("Flyway V4 import ledger tables are not installed")

        target_counts = {
            table: _fetch_scalar(cursor, f"SELECT COUNT(*) FROM `{table}`")
            for table in TARGET_TABLES
        }
        if any(target_counts.values()):
            raise MigrationError(
                "P4 target tables are not empty; refusing a full legacy import"
            )
        if _fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM legacy_import_run
            WHERE domain = %s AND source_sha256 = %s
            """,
            (DOMAIN, plan.source_sha256),
        ):
            raise MigrationError("this source SHA256 already has an import ledger entry")

        _start_transaction(connection)
        expected_json = json.dumps(plan.expected_counts, separators=(",", ":"))
        cursor.execute(
            """
            INSERT INTO legacy_import_run (
                run_id, domain, source_name, source_sha256, backup_sha256,
                source_size_bytes, status, expected_counts_json,
                imported_counts_json, reconciliation_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'RUNNING', %s, JSON_OBJECT(), JSON_OBJECT())
            """,
            (
                run_uuid,
                DOMAIN,
                plan.source_path.name,
                plan.source_sha256,
                backup_sha256,
                plan.source_size_bytes,
                expected_json,
            ),
        )
        ledger_id = int(cursor.lastrowid)

        owner_target_ids: dict[str, int] = {}
        for owner_id in plan.owners:
            username = _shadow_username(run_uuid, owner_id)
            cursor.execute(
                """
                INSERT INTO sys_user (
                    username, password_hash, status, security_version, version
                )
                VALUES (%s, %s, 'DISABLED', 0, 0)
                """,
                (username, f"!legacy-import-disabled:{uuid.uuid4()}"),
            )
            target_user_id = int(cursor.lastrowid)
            owner_target_ids[owner_id] = target_user_id
            cursor.execute(
                """
                INSERT INTO legacy_import_owner_map (
                    run_id, source_owner_id, target_user_id,
                    target_username, mapping_kind
                )
                VALUES (%s, %s, %s, %s, 'SHADOW')
                """,
                (ledger_id, owner_id, target_user_id, username),
            )

        conversation_target_ids: dict[str, int] = {}
        conversation_owner_target_ids: dict[str, int] = {}
        for item in plan.conversations:
            cursor.execute(
                """
                INSERT INTO conversation (
                    owner_id, title, status, context_version,
                    active_operation_id, version, created_at, updated_at,
                    last_message_at
                )
                VALUES (%s, %s, 'ACTIVE', 0, NULL, 0, %s, %s, %s)
                """,
                (
                    owner_target_ids[item.owner_id],
                    item.title,
                    item.created_at,
                    max(item.updated_at, item.last_message_at or item.updated_at),
                    item.last_message_at,
                ),
            )
            target_id = int(cursor.lastrowid)
            conversation_target_ids[item.session_id] = target_id
            conversation_owner_target_ids[item.session_id] = owner_target_ids[
                item.owner_id
            ]
            cursor.execute(
                """
                INSERT INTO legacy_import_id_map (
                    run_id, entity_type, source_id, target_id
                )
                VALUES (%s, 'CONVERSATION', %s, %s)
                """,
                (ledger_id, item.session_id, target_id),
            )

        message_target_ids: dict[tuple[int, str], int] = {}
        task_target_ids: dict[int, int] = {}
        task_request_hashes: dict[int, str] = {}
        for item in plan.qa_rows:
            turn_id = item.operation_id
            request_id = item.operation_id
            user_metadata = json.dumps(
                {"legacyImport": {"qaLogId": item.source_id, "source": "qa_log"}},
                separators=(",", ":"),
            )
            assistant_metadata = json.dumps(
                {
                    "legacyImport": {
                        "qaLogId": item.source_id,
                        "source": "qa_log",
                        "latencyMs": item.latency_ms,
                        "toolNames": list(item.tool_names),
                        "retrievedChunkCount": item.retrieved_chunk_count,
                        "responsePresent": item.response_present,
                        "sourceProjectionSha256": item.source_projection_hash,
                    }
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            evidence_status = (
                "UNAVAILABLE"
                if item.retrieved_chunk_count is None
                else ("SUPPORTED" if item.retrieved_chunk_count else "EMPTY")
            )
            for role, content, intent, risk, evidence, metadata in (
                ("USER", item.user_query, None, None, None, user_metadata),
                (
                    "ASSISTANT",
                    item.final_answer,
                    item.intent,
                    item.risk_level,
                    evidence_status,
                    assistant_metadata,
                ),
            ):
                cursor.execute(
                    """
                    INSERT INTO conversation_message (
                        conversation_id, turn_id, role, content, request_id,
                        status, intent, risk_level, evidence_status,
                        metadata_json, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'COMPLETED', %s, %s, %s, %s, %s)
                    """,
                    (
                        conversation_target_ids[item.session_id],
                        turn_id,
                        role,
                        content,
                        request_id,
                        intent,
                        risk,
                        evidence,
                        metadata,
                        item.created_at,
                    ),
                )
                message_id = int(cursor.lastrowid)
                message_target_ids[(item.source_id, role)] = message_id
                cursor.execute(
                    """
                    INSERT INTO legacy_import_id_map (
                        run_id, entity_type, source_id, target_id
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        ledger_id,
                        f"{role}_MESSAGE",
                        str(item.source_id),
                        message_id,
                    ),
                )

            assistant_message_id = message_target_ids[(item.source_id, "ASSISTANT")]
            task_request_hash = java_request_hash(
                conversation_id=conversation_target_ids[item.session_id],
                context_version=0,
                user_query=item.user_query,
            )
            task_request_hashes[item.source_id] = task_request_hash
            cursor.execute(
                """
                INSERT INTO biz_task (
                    owner_id, conversation_id, type, operation_id,
                    request_hash, executor_job_id, status, progress,
                    result_ref, error_code, retry_count, version,
                    created_at, started_at, finished_at
                )
                VALUES (
                    %s, %s, 'AI_QUERY', %s, %s, NULL, 'SUCCEEDED', 100,
                    %s, NULL, 0, 0, %s, %s, %s
                )
                """,
                (
                    conversation_owner_target_ids[item.session_id],
                    conversation_target_ids[item.session_id],
                    item.operation_id,
                    task_request_hash,
                    str(assistant_message_id),
                    item.created_at,
                    item.created_at,
                    item.created_at,
                ),
            )
            task_id = int(cursor.lastrowid)
            task_target_ids[item.source_id] = task_id
            cursor.execute(
                """
                INSERT INTO legacy_import_id_map (
                    run_id, entity_type, source_id, target_id
                )
                VALUES (%s, 'AI_QUERY_TASK', %s, %s)
                """,
                (ledger_id, str(item.source_id), task_id),
            )

        imported_counts = {
            "shadowUsers": _fetch_scalar(
                cursor,
                "SELECT COUNT(*) FROM legacy_import_owner_map WHERE run_id = %s",
                (ledger_id,),
            ),
            "conversations": _fetch_scalar(cursor, "SELECT COUNT(*) FROM conversation"),
            "messages": _fetch_scalar(cursor, "SELECT COUNT(*) FROM conversation_message"),
            "tasks": _fetch_scalar(cursor, "SELECT COUNT(*) FROM biz_task"),
            "idMaps": _fetch_scalar(
                cursor,
                "SELECT COUNT(*) FROM legacy_import_id_map WHERE run_id = %s",
                (ledger_id,),
            ),
        }
        if imported_counts != plan.expected_counts:
            raise MigrationError("post-import row counts do not match expected counts")

        cursor.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT entity_type, source_id)
            FROM legacy_import_id_map
            WHERE run_id = %s
            """,
            (ledger_id,),
        )
        map_count, distinct_source_map_count = (int(value) for value in cursor.fetchone())
        if map_count != distinct_source_map_count:
            raise MigrationError("post-import source ID uniqueness reconciliation failed")

        broken_foreign_keys = _fetch_scalar(
            cursor,
            """
            SELECT
                (SELECT COUNT(*)
                   FROM conversation c
                   LEFT JOIN sys_user u ON u.id = c.owner_id
                  WHERE u.id IS NULL)
              + (SELECT COUNT(*)
                   FROM conversation_message m
                   LEFT JOIN conversation c ON c.id = m.conversation_id
                  WHERE c.id IS NULL)
              + (SELECT COUNT(*)
                   FROM legacy_import_owner_map om
                   LEFT JOIN sys_user u ON u.id = om.target_user_id
                  WHERE om.run_id = %s AND u.id IS NULL)
              + (SELECT COUNT(*)
                   FROM biz_task t
                   LEFT JOIN sys_user u ON u.id = t.owner_id
                   LEFT JOIN conversation c ON c.id = t.conversation_id
                  WHERE u.id IS NULL OR c.id IS NULL)
            """,
            (ledger_id,),
        )
        if broken_foreign_keys:
            raise MigrationError("post-import foreign-key reconciliation failed")

        invalid_task_links = _fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM biz_task t
            LEFT JOIN conversation c ON c.id = t.conversation_id
            LEFT JOIN conversation_message m
              ON t.result_ref = CAST(m.id AS CHAR)
            WHERE t.type <> 'AI_QUERY'
               OR t.status <> 'SUCCEEDED'
               OR t.progress <> 100
               OR t.error_code IS NOT NULL
               OR t.created_at <> t.started_at
               OR t.started_at <> t.finished_at
               OR m.id IS NULL
               OR c.id IS NULL
               OR t.owner_id <> c.owner_id
               OR m.role <> 'ASSISTANT'
               OR m.conversation_id <> t.conversation_id
               OR m.turn_id <> t.operation_id
            """,
        )
        if invalid_task_links:
            raise MigrationError("post-import AI task reconciliation failed")

        mapped_task_count = _fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM legacy_import_id_map
            WHERE run_id = %s AND entity_type = 'AI_QUERY_TASK'
            """,
            (ledger_id,),
        )
        if mapped_task_count != len(plan.qa_rows):
            raise MigrationError("post-import AI task map count reconciliation failed")
        invalid_task_maps = _fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM legacy_import_id_map im
            LEFT JOIN biz_task t ON t.id = im.target_id
            WHERE im.run_id = %s
              AND im.entity_type = 'AI_QUERY_TASK'
              AND (
                  t.id IS NULL
                  OR t.operation_id <> CONCAT(%s, im.source_id)
              )
            """,
            (ledger_id, f"legacy-p4-{plan.source_sha256[:16]}-qa-"),
        )
        if invalid_task_maps:
            raise MigrationError("post-import AI task map reconciliation failed")
        cursor.execute(
            """
            SELECT im.source_id, t.operation_id, t.request_hash
            FROM legacy_import_id_map im
            JOIN biz_task t ON t.id = im.target_id
            WHERE im.run_id = %s AND im.entity_type = 'AI_QUERY_TASK'
            """,
            (ledger_id,),
        )
        expected_task_projection = {
            str(item.source_id): (
                item.operation_id,
                task_request_hashes[item.source_id],
            )
            for item in plan.qa_rows
        }
        validate_task_map_projection(cursor.fetchall(), expected_task_projection)

        source_time_range = _source_time_range(plan)
        cursor.execute(
            """
            SELECT MIN(created_at), MAX(created_at)
            FROM (
                SELECT created_at FROM conversation
                UNION ALL
                SELECT created_at FROM conversation_message
            ) AS imported_timestamps
            """
        )
        target_minimum, target_maximum = cursor.fetchone()
        if source_time_range is None:
            target_time_range = None
            if target_minimum is not None or target_maximum is not None:
                raise MigrationError("post-import time-range reconciliation failed")
        else:
            if target_minimum is None or target_maximum is None:
                raise MigrationError("post-import time-range reconciliation failed")
            target_time_range = (
                parse_legacy_time(target_minimum, field="target minimum created_at"),
                parse_legacy_time(target_maximum, field="target maximum created_at"),
            )
            if target_time_range != source_time_range:
                raise MigrationError("post-import time-range reconciliation failed")

        samples: list[dict[str, Any]] = []
        qa_by_id = {item.source_id: item for item in plan.qa_rows}
        for source_id in _sample_source_ids(plan.qa_rows):
            item = qa_by_id[source_id]
            for role, source_content, intent, risk in (
                ("USER", item.user_query, None, None),
                ("ASSISTANT", item.final_answer, item.intent, item.risk_level),
            ):
                target_id = message_target_ids[(source_id, role)]
                cursor.execute(
                    """
                    SELECT role, content, intent, risk_level
                    FROM conversation_message
                    WHERE id = %s
                    """,
                    (target_id,),
                )
                target = cursor.fetchone()
                source_fingerprint = _message_fingerprint(
                    role, source_content, intent, risk
                )
                target_fingerprint = _message_fingerprint(
                    str(target[0]), str(target[1]), target[2], target[3]
                )
                if source_fingerprint != target_fingerprint:
                    raise MigrationError("sample content reconciliation failed")
                samples.append(
                    {
                        "qaLogId": source_id,
                        "role": role,
                        "sha256": source_fingerprint,
                        "match": True,
                    }
                )
            cursor.execute(
                """
                SELECT t.id, t.operation_id, t.request_hash, t.result_ref
                FROM legacy_import_id_map im
                JOIN biz_task t ON t.id = im.target_id
                WHERE im.run_id = %s
                  AND im.entity_type = 'AI_QUERY_TASK'
                  AND im.source_id = %s
                """,
                (ledger_id, str(source_id)),
            )
            task_sample = cursor.fetchone()
            if task_sample is None:
                raise MigrationError("sample AI task map reconciliation failed")
            task_id, operation_id, request_hash, result_ref = task_sample
            expected_result_ref = str(
                message_target_ids[(source_id, "ASSISTANT")]
            )
            if (
                int(task_id) != task_target_ids[source_id]
                or str(operation_id) != item.operation_id
                or str(request_hash) != task_request_hashes[source_id]
                or str(result_ref) != expected_result_ref
            ):
                raise MigrationError("sample AI task reconciliation failed")
            samples.append(
                {
                    "qaLogId": source_id,
                    "entityType": "AI_QUERY_TASK",
                    "requestHash": task_request_hashes[source_id],
                    "match": True,
                }
            )

        _ensure_quiescent_source(plan.source_path)
        if sha256_file(plan.source_path) != plan.source_sha256:
            raise MigrationError("SQLite source changed during the MySQL transaction")
        if os.path.samefile(plan.source_path, backup_path):
            raise MigrationError("backup is not independent from the SQLite source")
        _ensure_quiescent_source(backup_path, label="SQLite backup")
        if sha256_file(backup_path) != backup_sha256:
            raise MigrationError("backup changed during the MySQL transaction")

        reconciliation = {
            "countsMatch": True,
            "uniqueSourceMaps": True,
            "foreignKeys": "ok",
            "aiQueryTasks": "ok",
            "timeRangeUtc": (
                {
                    "min": source_time_range[0].isoformat(timespec="microseconds") + "Z",
                    "max": source_time_range[1].isoformat(timespec="microseconds") + "Z",
                    "match": True,
                }
                if source_time_range is not None
                else None
            ),
            "sampleContent": samples,
            "sourceSha256Rechecked": True,
            "warnings": list(plan.warnings),
        }
        imported_json = json.dumps(imported_counts, separators=(",", ":"))
        reconciliation_json = json.dumps(
            reconciliation, ensure_ascii=False, separators=(",", ":")
        )
        cursor.execute(
            """
            UPDATE legacy_import_run
            SET status = 'SUCCEEDED',
                imported_counts_json = %s,
                reconciliation_json = %s,
                finished_at = CURRENT_TIMESTAMP(6)
            WHERE id = %s AND status = 'RUNNING'
            """,
            (imported_json, reconciliation_json, ledger_id),
        )
        if cursor.rowcount != 1:
            raise MigrationError("could not finalize the import ledger")
        cursor.execute(
            """
            INSERT INTO audit_log (
                actor_id, action, resource_type, resource_id, request_id,
                result, client_ip, user_agent, detail_json
            )
            VALUES (
                NULL, 'LEGACY_IMPORT_COMPLETED', 'LEGACY_IMPORT_RUN', %s, %s,
                'SUCCESS', NULL, 'p4-migration-script', %s
            )
            """,
            (
                str(ledger_id),
                run_uuid,
                json.dumps(
                    {
                        "domain": DOMAIN,
                        "sourceSha256": plan.source_sha256,
                        "counts": imported_counts,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        connection.commit()
        return {
            "mode": "apply",
            "status": "succeeded",
            "runId": run_uuid,
            "ledgerId": ledger_id,
            "domain": DOMAIN,
            "sourceSha256": plan.source_sha256,
            "backupSha256": backup_sha256,
            "importedCounts": imported_counts,
            "reconciliation": reconciliation,
        }
    except Exception:
        try:
            connection.rollback()
        except Exception:
            pass
        raise
    finally:
        if acquired:
            try:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
                cursor.fetchone()
            except Exception:
                pass
        cursor.close()


def _verify_backup(source: Path, backup: Path | None, expected_sha: str, apply: bool) -> str | None:
    if backup is None:
        if apply:
            raise MigrationError("--backup is required with --apply")
        return None
    backup = backup.resolve()
    if not backup.is_file():
        raise MigrationError("backup does not exist or is not a regular file")
    if backup == source.resolve() or os.path.samefile(source, backup):
        raise MigrationError("--backup must be a distinct file from --source")
    _ensure_quiescent_source(backup, label="SQLite backup")
    backup_hash = sha256_file(backup)
    if backup_hash != expected_sha:
        raise MigrationError("backup SHA256 does not match the source SHA256")
    return backup_hash


def _write_report(report: dict[str, Any], destination: Path | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply the offline P4 SQLite to MySQL migration."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument(
        "--backup",
        type=Path,
        help="Existing byte-for-byte backup; mandatory with --apply.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all source checks without connecting to MySQL (the default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply in one MySQL transaction. Default behavior is dry-run.",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--lock-timeout-seconds", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.lock_timeout_seconds < 0 or arguments.lock_timeout_seconds > 60:
            raise MigrationError("--lock-timeout-seconds must be between 0 and 60")
        expected = normalize_sha256(arguments.expected_sha256)
        plan = build_import_plan(arguments.source, expected)
        backup_sha = _verify_backup(
            plan.source_path,
            arguments.backup,
            expected,
            arguments.apply,
        )
        if arguments.apply:
            if sha256_file(plan.source_path) != plan.source_sha256:
                raise MigrationError("SQLite source changed after preflight")
            connection = connect_mysql()
            try:
                report = apply_import(
                    plan,
                    arguments.backup.resolve(),
                    backup_sha or "",
                    connection,
                    lock_timeout_seconds=arguments.lock_timeout_seconds,
                )
            finally:
                connection.close()
        else:
            report = dry_run_report(plan, backup_sha)
        _write_report(report, arguments.report)
        return 0
    except MigrationError as exc:
        print(f"migration refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"migration failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
