from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4


ClaimState = Literal["created", "recovered", "replay", "conflict"]
TERMINAL_STATUSES = ("SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExecutionClaim:
    state: ClaimState
    record: dict[str, Any] | None


class AiExecutionRecordRepository:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        ttl_hours: int = 24,
        running_lease_seconds: int = 90,
    ) -> None:
        self.conn = conn
        self.ttl_hours = ttl_hours
        self.running_lease_seconds = running_lease_seconds
        self._lock = threading.RLock()

    def claim(
        self,
        *,
        operation_id: str,
        idempotency_key: str,
        operation_type: str,
        request_id: str,
        request_hash: str,
        initial_status: str = "RUNNING",
        request_payload: dict[str, Any] | None = None,
    ) -> ExecutionClaim:
        with self._lock:
            now = utc_now()
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                self._delete_expired(now)
                existing = self._claim_from_existing(
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    operation_type=operation_type,
                    request_hash=request_hash,
                    now=now,
                )
                if existing is not None:
                    self.conn.commit()
                    return existing

                expires_at = now + timedelta(hours=self.ttl_hours)
                run_id = f"run_{uuid4().hex}"
                self.conn.execute(
                    """
                    INSERT INTO ai_execution_record (
                        operation_id, idempotency_key, operation_type, request_id,
                        request_hash, run_id, status, progress, request_json, created_at,
                        started_at, updated_at, expires_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation_id,
                        idempotency_key,
                        operation_type,
                        request_id,
                        request_hash,
                        run_id,
                        initial_status,
                        0,
                        self._encode(request_payload),
                        now.isoformat(),
                        now.isoformat() if initial_status == "RUNNING" else None,
                        now.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                self.conn.rollback()
                self.conn.execute("BEGIN IMMEDIATE")
                existing = self._claim_from_existing(
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    operation_type=operation_type,
                    request_hash=request_hash,
                    now=now,
                )
                self.conn.commit()
                return existing or ExecutionClaim("conflict", None)
            row = self.conn.execute(
                "SELECT * FROM ai_execution_record WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            return ExecutionClaim("created", self._decode(row))

    def complete(
        self,
        operation_id: str,
        result: dict[str, Any],
        *,
        progress: int = 100,
    ) -> dict[str, Any]:
        return self._finish(
            operation_id,
            status="SUCCEEDED",
            progress=progress,
            result=result,
            error=None,
        )

    def fail(
        self,
        operation_id: str,
        error: dict[str, Any],
        *,
        status: str = "FAILED",
    ) -> dict[str, Any]:
        return self._finish(
            operation_id,
            status=status,
            progress=100,
            result=None,
            error=error,
        )

    def get(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                self._delete_expired(utc_now())
                row = self.conn.execute(
                    "SELECT * FROM ai_execution_record WHERE operation_id = ?",
                    (operation_id,),
                ).fetchone()
                self.conn.commit()
                return self._decode(row) if row is not None else None
            except Exception:
                self.conn.rollback()
                raise

    def claim_next(
        self,
        *,
        operation_type: str,
        lease_seconds: int,
    ) -> dict[str, Any] | None:
        """Atomically claim one queued or abandoned asynchronous execution."""
        with self._lock:
            now = utc_now()
            lease_token = f"lease_{uuid4().hex}"
            lease_expires_at = now + timedelta(seconds=lease_seconds)
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                self._delete_expired(now)
                row = self.conn.execute(
                    """
                    SELECT operation_id
                    FROM ai_execution_record
                    WHERE operation_type = ?
                      AND (
                        status = 'ACCEPTED'
                        OR (
                          status = 'RUNNING'
                          AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                        )
                      )
                    ORDER BY created_at, operation_id
                    LIMIT 1
                    """,
                    (operation_type, now.isoformat()),
                ).fetchone()
                if row is None:
                    self.conn.commit()
                    return None
                cursor = self.conn.execute(
                    """
                    UPDATE ai_execution_record
                    SET status = 'RUNNING',
                        progress = CASE WHEN progress < 5 THEN 5 ELSE progress END,
                        lease_token = ?,
                        lease_expires_at = ?,
                        attempt_count = attempt_count + 1,
                        started_at = COALESCE(started_at, ?),
                        updated_at = ?
                    WHERE operation_id = ?
                      AND (
                        status = 'ACCEPTED'
                        OR (
                          status = 'RUNNING'
                          AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                        )
                      )
                    """,
                    (
                        lease_token,
                        lease_expires_at.isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                        row["operation_id"],
                        now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    self.conn.rollback()
                    return None
                claimed = self.conn.execute(
                    "SELECT * FROM ai_execution_record WHERE operation_id = ?",
                    (row["operation_id"],),
                ).fetchone()
                self.conn.commit()
                return self._decode(claimed)
            except Exception:
                self.conn.rollback()
                raise

    def renew_lease(
        self,
        operation_id: str,
        lease_token: str,
        *,
        lease_seconds: int,
        progress: int,
    ) -> bool:
        with self._lock:
            now = utc_now()
            cursor = self.conn.execute(
                """
                UPDATE ai_execution_record
                SET progress = ?, updated_at = ?, lease_expires_at = ?
                WHERE operation_id = ? AND status = 'RUNNING' AND lease_token = ?
                """,
                (
                    progress,
                    now.isoformat(),
                    (now + timedelta(seconds=lease_seconds)).isoformat(),
                    operation_id,
                    lease_token,
                ),
            )
            self.conn.commit()
            return cursor.rowcount == 1

    def complete_leased(
        self,
        operation_id: str,
        lease_token: str,
        result: dict[str, Any],
    ) -> bool:
        return self._finish_leased(
            operation_id,
            lease_token,
            status="SUCCEEDED",
            result=result,
            error=None,
        )

    def fail_leased(
        self,
        operation_id: str,
        lease_token: str,
        error: dict[str, Any],
        *,
        status: str = "FAILED",
    ) -> bool:
        return self._finish_leased(
            operation_id,
            lease_token,
            status=status,
            result=None,
            error=error,
        )

    def _finish_leased(
        self,
        operation_id: str,
        lease_token: str,
        *,
        status: str,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> bool:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"invalid terminal status: {status}")
        with self._lock:
            now = utc_now().isoformat()
            cursor = self.conn.execute(
                """
                UPDATE ai_execution_record
                SET status = ?, progress = 100, result_json = ?, error_json = ?,
                    lease_token = NULL, lease_expires_at = NULL,
                    updated_at = ?, finished_at = ?
                WHERE operation_id = ? AND status = 'RUNNING' AND lease_token = ?
                """,
                (
                    status,
                    self._encode(result),
                    self._encode(error),
                    now,
                    now,
                    operation_id,
                    lease_token,
                ),
            )
            self.conn.commit()
            return cursor.rowcount == 1

    def _finish(
        self,
        operation_id: str,
        *,
        status: str,
        progress: int,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
    ) -> dict[str, Any]:
        with self._lock:
            now = utc_now().isoformat()
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                cursor = self.conn.execute(
                    """
                    UPDATE ai_execution_record
                    SET status = ?,
                        progress = ?,
                        result_json = ?,
                        error_json = ?,
                        updated_at = ?,
                        finished_at = ?
                    WHERE operation_id = ?
                      AND status IN ('RUNNING', 'ACCEPTED')
                    """,
                    (
                        status,
                        progress,
                        self._encode(result),
                        self._encode(error),
                        now,
                        now,
                        operation_id,
                    ),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            record = self.get(operation_id)
            if record is None:
                raise LookupError(f"execution record not found: {operation_id}")
            if cursor.rowcount == 0 and record["status"] not in {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"}:
                raise RuntimeError(f"execution record is not finishable: {operation_id}")
            return record

    def _delete_expired(self, now: datetime) -> None:
        self.conn.execute(
            """
            DELETE FROM ai_execution_record
            WHERE expires_at <= ?
              AND status IN ('SUCCEEDED', 'FAILED', 'TIMED_OUT', 'CANCELLED')
            """,
            (now.isoformat(),),
        )

    def _claim_from_existing(
        self,
        *,
        operation_id: str,
        idempotency_key: str,
        operation_type: str,
        request_hash: str,
        now: datetime,
    ) -> ExecutionClaim | None:
        rows = self.conn.execute(
            """
            SELECT * FROM ai_execution_record
            WHERE operation_id = ?
               OR idempotency_key = ?
            """,
            (operation_id, idempotency_key),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            return ExecutionClaim("conflict", None)
        record = self._decode(rows[0])
        matches = (
            record["operation_id"] == operation_id
            and record["idempotency_key"] == idempotency_key
            and record["operation_type"] == operation_type
            and record["request_hash"] == request_hash
        )
        if matches and self._running_lease_expired(record, now):
            refreshed_expiry = now + timedelta(hours=self.ttl_hours)
            self.conn.execute(
                """
                UPDATE ai_execution_record
                SET progress = 0,
                    result_json = NULL,
                    error_json = NULL,
                    started_at = ?,
                    updated_at = ?,
                    finished_at = NULL,
                    expires_at = ?
                WHERE operation_id = ?
                  AND status = 'RUNNING'
                """,
                (
                    now.isoformat(),
                    now.isoformat(),
                    refreshed_expiry.isoformat(),
                    operation_id,
                ),
            )
            row = self.conn.execute(
                "SELECT * FROM ai_execution_record WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            return ExecutionClaim("recovered", self._decode(row))
        return ExecutionClaim("replay" if matches else "conflict", record if matches else None)

    def _running_lease_expired(self, record: dict[str, Any], now: datetime) -> bool:
        if record.get("status") != "RUNNING":
            return False
        updated_at = datetime.fromisoformat(record["updated_at"])
        return updated_at <= now - timedelta(seconds=self.running_lease_seconds)

    @staticmethod
    def _encode(value: dict[str, Any] | None) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        request_json = record.pop("request_json", None)
        result_json = record.pop("result_json", None)
        error_json = record.pop("error_json", None)
        record["request"] = json.loads(request_json) if request_json else None
        record["result"] = json.loads(result_json) if result_json else None
        record["error"] = json.loads(error_json) if error_json else None
        return record
