from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.config import Settings
from backend.app.core.internal_api import canonical_request_hash
from backend.app.db.ai_execution_repository import AiExecutionRecordRepository
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.main import create_app


def _repository() -> tuple[AiExecutionRecordRepository, object]:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    return AiExecutionRecordRepository(conn, ttl_hours=24), conn


def _claim(
    repository: AiExecutionRecordRepository,
    *,
    operation_id: str = "op_execution_0001",
    idempotency_key: str = "idem_execution_0001",
    operation_type: str = "AI_CHAT",
    request_id: str = "req_execution_0001",
    request_hash: str = "a" * 64,
):
    return repository.claim(
        operation_id=operation_id,
        idempotency_key=idempotency_key,
        operation_type=operation_type,
        request_id=request_id,
        request_hash=request_hash,
    )


def test_execution_record_schema_has_reconciliation_and_expiry_constraints() -> None:
    _repository_instance, conn = _repository()

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(ai_execution_record)").fetchall()
    }
    indexes = {
        row["name"]
        for row in conn.execute("PRAGMA index_list(ai_execution_record)").fetchall()
    }

    assert {
        "operation_id",
        "idempotency_key",
        "operation_type",
        "request_id",
        "request_hash",
        "run_id",
        "status",
        "progress",
        "request_json",
        "lease_token",
        "lease_expires_at",
        "attempt_count",
        "result_json",
        "error_json",
        "created_at",
        "started_at",
        "updated_at",
        "finished_at",
        "expires_at",
    } <= columns
    assert "idx_ai_execution_expires_at" in indexes
    assert "idx_ai_execution_status_updated" in indexes


def test_claim_replays_same_operation_without_creating_a_second_record() -> None:
    repository, conn = _repository()

    first = _claim(repository)
    replay = _claim(repository)

    assert first.state == "created"
    assert replay.state == "replay"
    assert replay.record == first.record
    assert first.record is not None
    assert first.record["status"] == "RUNNING"
    assert first.record["run_id"].startswith("run_")
    assert (
        conn.execute("SELECT COUNT(*) FROM ai_execution_record").fetchone()[0]
        == 1
    )


def test_stale_running_claim_is_recovered_once_with_same_run_id() -> None:
    repository, conn = _repository()
    first = _claim(repository)
    stale_at = (datetime.now(timezone.utc) - timedelta(seconds=91)).isoformat()
    conn.execute(
        "UPDATE ai_execution_record SET updated_at = ? WHERE operation_id = ?",
        (stale_at, "op_execution_0001"),
    )
    conn.commit()

    recovered = _claim(repository)
    replay = _claim(repository)

    assert first.record is not None
    assert recovered.state == "recovered"
    assert recovered.record is not None
    assert recovered.record["run_id"] == first.record["run_id"]
    assert recovered.record["updated_at"] != stale_at
    assert replay.state == "replay"


def test_concurrent_stale_claim_has_single_recovery_winner() -> None:
    repository, conn = _repository()
    _claim(repository)
    stale_at = (datetime.now(timezone.utc) - timedelta(seconds=91)).isoformat()
    conn.execute(
        "UPDATE ai_execution_record SET updated_at = ? WHERE operation_id = ?",
        (stale_at, "op_execution_0001"),
    )
    conn.commit()

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda _index: _claim(repository), range(16)))

    assert sum(claim.state == "recovered" for claim in claims) == 1
    assert sum(claim.state == "replay" for claim in claims) == 15
    assert len({claim.record["run_id"] for claim in claims if claim.record}) == 1


@pytest.mark.parametrize(
    ("operation_id", "idempotency_key"),
    [
        ("op_execution_0001", "idem_execution_changed_0001"),
        ("op_execution_changed_0001", "idem_execution_0001"),
    ],
)
def test_operation_or_idempotency_binding_conflict_is_detected(
    operation_id: str,
    idempotency_key: str,
) -> None:
    repository, conn = _repository()
    _claim(repository)

    conflict = _claim(
        repository,
        operation_id=operation_id,
        idempotency_key=idempotency_key,
        request_hash="b" * 64,
    )

    assert conflict.state == "conflict"
    assert conflict.record is None
    assert (
        conn.execute("SELECT COUNT(*) FROM ai_execution_record").fetchone()[0]
        == 1
    )


def test_completed_result_is_persisted_for_response_loss_reconciliation() -> None:
    repository, _conn = _repository()
    claim = _claim(repository)
    assert claim.record is not None
    result = {
        "requestId": "req_execution_0001",
        "operationId": "op_execution_0001",
        "outcome": "ANSWERED",
        "answer": "grounded answer",
    }

    completed = repository.complete("op_execution_0001", result)
    reconciled = repository.get("op_execution_0001")

    assert completed["status"] == "SUCCEEDED"
    assert completed["progress"] == 100
    assert completed["result"] == result
    assert completed["error"] is None
    assert completed["finished_at"] is not None
    assert reconciled == completed
    assert reconciled["run_id"] == claim.record["run_id"]


def test_failed_execution_persists_safe_machine_readable_error() -> None:
    repository, _conn = _repository()
    _claim(repository)
    error = {
        "code": "RAG_UNAVAILABLE",
        "message": "RAG dependency unavailable",
        "retryable": True,
        "details": {},
    }

    failed = repository.fail("op_execution_0001", error)

    assert failed["status"] == "FAILED"
    assert failed["result"] is None
    assert failed["error"] == error
    assert failed["finished_at"] is not None


def test_terminal_execution_record_cannot_be_overwritten() -> None:
    repository, _conn = _repository()
    _claim(repository)
    completed = repository.complete("op_execution_0001", {"outcome": "ANSWERED"})

    replayed_finish = repository.fail(
        "op_execution_0001",
        {
            "code": "INTERNAL_ERROR",
            "message": "late failure",
            "retryable": False,
            "details": {},
        },
    )

    assert replayed_finish == completed
    assert replayed_finish["status"] == "SUCCEEDED"
    assert replayed_finish["result"] == {"outcome": "ANSWERED"}
    assert replayed_finish["error"] is None


def test_expired_execution_is_deleted_and_returns_not_found() -> None:
    repository, conn = _repository()
    _claim(repository)
    repository.complete("op_execution_0001", {"outcome": "ANSWERED"})
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    conn.execute(
        "UPDATE ai_execution_record SET expires_at = ? WHERE operation_id = ?",
        (expired_at, "op_execution_0001"),
    )
    conn.commit()

    record = repository.get("op_execution_0001")

    assert record is None
    assert (
        conn.execute("SELECT COUNT(*) FROM ai_execution_record").fetchone()[0]
        == 0
    )


def test_expired_active_execution_is_retained_for_recovery() -> None:
    repository, conn = _repository()
    _claim(repository)
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    conn.execute(
        "UPDATE ai_execution_record SET expires_at = ? WHERE operation_id = ?",
        (expired_at, "op_execution_0001"),
    )
    conn.commit()

    record = repository.get("op_execution_0001")

    assert record is not None
    assert record["status"] == "RUNNING"


def test_concurrent_identical_claim_creates_only_one_execution() -> None:
    repository, conn = _repository()

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda _index: _claim(repository), range(16)))

    assert sum(claim.state == "created" for claim in claims) == 1
    assert sum(claim.state == "replay" for claim in claims) == 15
    assert {claim.record["run_id"] for claim in claims if claim.record} == {
        claims[0].record["run_id"]
    }
    assert (
        conn.execute("SELECT COUNT(*) FROM ai_execution_record").fetchone()[0]
        == 1
    )


def test_canonical_hash_is_stable_and_does_not_persist_raw_request_payload() -> None:
    repository, conn = _repository()
    payload_a = {
        "requestId": "req_execution_hash_0001",
        "operationId": "op_execution_hash_0001",
        "query": "sensitive consultation text",
        "history": [],
    }
    payload_b = {
        "history": [],
        "query": "sensitive consultation text",
        "operationId": "op_execution_hash_0001",
        "requestId": "req_execution_hash_0001",
    }
    request_hash = canonical_request_hash("AI_CHAT", payload_a)

    assert request_hash == canonical_request_hash("AI_CHAT", payload_b)
    assert request_hash != canonical_request_hash(
        "AI_CHAT",
        {**payload_b, "query": "different request"},
    )

    claim = _claim(
        repository,
        operation_id=payload_a["operationId"],
        request_id=payload_a["requestId"],
        request_hash=request_hash,
    )
    raw_row = conn.execute(
        "SELECT * FROM ai_execution_record WHERE operation_id = ?",
        (payload_a["operationId"],),
    ).fetchone()

    assert claim.state == "created"
    assert raw_row["request_hash"] == request_hash
    assert "sensitive consultation text" not in str(tuple(raw_row))


def test_execution_store_commit_does_not_commit_legacy_business_transaction() -> None:
    app = create_app(
        Settings(
            database={"url": "sqlite:///:memory:"},
            internal_api={"service_token": "test-service-token"},
        )
    )
    assert app.state.execution_db_conn is not app.state.db_conn
    app.state.db_conn.execute(
        "INSERT INTO conversation (session_id, owner_id, title) VALUES (?, ?, ?)",
        ("conv_uncommitted", "user_1", "uncommitted"),
    )

    claim = app.state.ai_execution_repository.claim(
        operation_id="op_isolation_0001",
        idempotency_key="idem_isolation_0001",
        operation_type="AI_CHAT",
        request_id="req_isolation_0001",
        request_hash="c" * 64,
    )
    app.state.db_conn.rollback()

    assert claim.state == "created"
    assert (
        app.state.db_conn.execute(
            "SELECT COUNT(*) FROM conversation WHERE session_id = ?",
            ("conv_uncommitted",),
        ).fetchone()[0]
        == 0
    )
