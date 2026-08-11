from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.db.ai_execution_repository import AiExecutionRecordRepository
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.main import create_app
from backend.app.services.knowledge_ingestion_service import (
    KnowledgeIngestionFailure,
    KnowledgeIngestionService,
)


SERVICE_TOKEN = "test-java-service-token-32-characters"


def _settings(root: Path, execution_db: Path, *, worker_enabled: bool = True) -> Settings:
    return Settings(
        database={"url": "sqlite:///:memory:"},
        internal_api={
            "service_token": SERVICE_TOKEN,
            "execution_database_url": f"sqlite:///{execution_db}",
            "shared_upload_root": str(root),
            "ingestion_worker_enabled": worker_enabled,
            "ingestion_poll_interval_seconds": 0.05,
            "ingestion_lease_seconds": 5,
        },
    )


def _document(root: Path, *, content: bytes = b"healthy livestock\n") -> tuple[Path, dict]:
    path = root / "users" / "user_1" / "documents" / "guide.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    payload = {
        "requestId": "req_ingestion_0001",
        "operationId": "op_ingestion_0001",
        "userId": "user_1",
        "documentId": "doc_0001",
        "collection": "test",
        "objectKey": "users/user_1/documents/guide.txt",
        "fileName": "guide.txt",
        "mediaType": "text/plain",
        "sizeBytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "force": False,
    }
    return path, payload


def _headers(request_id: str, idempotency_key: str = "idem_ingestion_0001") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SERVICE_TOKEN}",
        "X-Request-ID": request_id,
        "Idempotency-Key": idempotency_key,
    }


def _wait_for_terminal(client: TestClient, operation_id: str) -> dict:
    for _index in range(100):
        response = client.get(
            f"/internal/v1/ai/operations/{operation_id}",
            headers={
                "Authorization": f"Bearer {SERVICE_TOKEN}",
                "X-Request-ID": "req_ingestion_poll_0001",
            },
        )
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"}:
            return body
        time.sleep(0.02)
    raise AssertionError("document ingestion did not reach a terminal state")


def test_document_ingestion_survives_restart_and_terminal_post_replays(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    _path, payload = _document(root)
    execution_db = tmp_path / "execution.db"

    with TestClient(create_app(_settings(root, execution_db, worker_enabled=False))) as first:
        accepted = first.post(
            "/internal/v1/ai/knowledge/ingestions",
            headers=_headers(payload["requestId"]),
            json=payload,
        )
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "ACCEPTED"
        assert accepted.json()["runId"].startswith("run_")

    with TestClient(create_app(_settings(root, execution_db))) as restarted:
        completed = _wait_for_terminal(restarted, payload["operationId"])
        assert completed["status"] == "SUCCEEDED"
        assert completed["result"] == {
            "documentId": "doc_0001",
            "ragDocumentId": payload["sha256"],
            "collection": "test",
            "indexed": False,
            "skipped": False,
            "chunkCount": 0,
            "executionMode": "FAKE",
        }

        replay = restarted.post(
            "/internal/v1/ai/knowledge/ingestions",
            headers=_headers(payload["requestId"]),
            json=payload,
        )
        assert replay.status_code == 202
        assert replay.json()["status"] == "SUCCEEDED"
        assert replay.json()["runId"] == completed["runId"]


def test_worker_persists_safe_file_validation_failure(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    path, payload = _document(root)
    path.write_bytes(b"tampered")

    with TestClient(create_app(_settings(root, tmp_path / "execution.db"))) as client:
        response = client.post(
            "/internal/v1/ai/knowledge/ingestions",
            headers=_headers(payload["requestId"]),
            json=payload,
        )
        assert response.status_code == 202
        failed = _wait_for_terminal(client, payload["operationId"])

    assert failed["status"] == "FAILED"
    assert failed["result"] is None
    assert failed["error"]["code"] == "OBJECT_SIZE_MISMATCH"
    assert str(root) not in failed["error"]["message"]


def test_expired_lease_is_recovered_and_old_worker_is_fenced(tmp_path: Path) -> None:
    conn = get_connection(f"sqlite:///{tmp_path / 'leases.db'}")
    init_db(conn)
    repository = AiExecutionRecordRepository(conn)
    payload = {"documentId": "doc_lease", "objectKey": "objects/doc.txt"}
    repository.claim(
        operation_id="op_ingestion_lease_0001",
        idempotency_key="idem_ingestion_lease_0001",
        operation_type="DOCUMENT_INDEX",
        request_id="req_ingestion_lease_0001",
        request_hash="a" * 64,
        initial_status="ACCEPTED",
        request_payload=payload,
    )

    first = repository.claim_next(operation_type="DOCUMENT_INDEX", lease_seconds=30)
    assert first is not None
    conn.execute(
        "UPDATE ai_execution_record SET lease_expires_at = ? WHERE operation_id = ?",
        (
            (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "op_ingestion_lease_0001",
        ),
    )
    conn.commit()
    second = repository.claim_next(operation_type="DOCUMENT_INDEX", lease_seconds=30)

    assert second is not None
    assert second["attempt_count"] == 2
    assert second["lease_token"] != first["lease_token"]
    assert repository.complete_leased(
        "op_ingestion_lease_0001", first["lease_token"], {"late": True}
    ) is False
    assert repository.fail_leased(
        "op_ingestion_lease_0001",
        second["lease_token"],
        {"code": "FAILED", "message": "safe failure", "retryable": False, "details": {}},
    ) is True


def test_service_rejects_missing_object(
    tmp_path: Path,
) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    _path, payload = _document(root)
    payload["objectKey"] = "users/user_1/documents/missing.txt"

    with pytest.raises(KnowledgeIngestionFailure) as error:
        KnowledgeIngestionService(_settings(root, tmp_path / "unused.db")).execute(payload)

    assert error.value.code == "OBJECT_NOT_FOUND"


def test_service_rejects_symlink_segment_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    _path, payload = _document(root)
    original = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path.name == "documents" or original(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(KnowledgeIngestionFailure) as error:
        KnowledgeIngestionService(_settings(root, tmp_path / "unused.db")).execute(payload)

    assert error.value.code == "OBJECT_KEY_SYMLINK"
