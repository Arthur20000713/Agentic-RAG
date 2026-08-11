from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.main import create_app


TOKEN = "test-java-service-token-32-characters"


class IncludeStatsRecordingRagClient(FakeRagServerClient):
    def __init__(self) -> None:
        super().__init__()
        self.include_stats: bool | None = None

    async def list_collections(self, *, include_stats: bool = True) -> list[str]:
        self.include_stats = include_stats
        return await super().list_collections(include_stats=include_stats)


def _client(settings: Settings | None = None) -> tuple[TestClient, object]:
    app = create_app(
        settings
        or Settings(
            database={"url": "sqlite:///:memory:"},
            internal_api={"service_token": TOKEN},
        )
    )
    return TestClient(app), app


def _headers(request_id: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Request-ID": request_id,
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def test_internal_rag_collection_and_summary_contracts() -> None:
    client, app = _client()
    recording_client = IncludeStatsRecordingRagClient()
    app.state.rag_client = recording_client

    collections = client.get(
        "/internal/v1/rag/collections?includeStats=false",
        headers=_headers("req_rag_collections_0001"),
    )
    summary = client.get(
        "/internal/v1/rag/collections/default/documents/doc_001/summary",
        headers=_headers("req_rag_summary_0001"),
    )

    assert collections.status_code == 200
    assert [item["name"] for item in collections.json()["collections"]] == ["default", "test"]
    assert recording_client.include_stats is False
    assert collections.headers["X-Request-ID"] == "req_rag_collections_0001"
    assert summary.status_code == 200
    body = summary.json()
    assert body["collection"] == "default"
    assert body["documentId"] == "doc_001"
    assert body["summary"]
    assert body["sourceUriPrefix"].startswith("rag://default/doc_001")


def test_document_ingestion_is_persisted_as_reconcilable_accepted_operation() -> None:
    client, _app = _client()
    payload = {
        "requestId": "req_ingestion_0001",
        "operationId": "op_ingestion_0001",
        "userId": "user_ingestion_0001",
        "documentId": "doc_ingestion_0001",
        "collection": "default",
        "objectKey": "users/user_ingestion_0001/documents/guide.pdf",
        "fileName": "guide.pdf",
        "mediaType": "application/pdf",
        "sizeBytes": 1024,
        "sha256": "a" * 64,
        "force": False,
    }

    created = client.post(
        "/internal/v1/ai/knowledge/ingestions",
        headers=_headers("req_ingestion_0001", idempotency_key="idem_ingestion_0001"),
        json=payload,
    )
    replay = client.post(
        "/internal/v1/ai/knowledge/ingestions",
        headers=_headers("req_ingestion_0001", idempotency_key="idem_ingestion_0001"),
        json=payload,
    )
    lookup = client.get(
        "/internal/v1/ai/operations/op_ingestion_0001",
        headers=_headers("req_ingestion_lookup_0001"),
    )

    assert created.status_code == 202
    assert created.headers["Location"] == "/internal/v1/ai/operations/op_ingestion_0001"
    assert replay.status_code == 202
    assert replay.json() == created.json()
    assert created.json()["status"] == "ACCEPTED"
    assert lookup.status_code == 200
    assert lookup.json()["status"] == "ACCEPTED"
    assert lookup.json()["type"] == "DOCUMENT_INDEX"


def test_ingestion_rejects_parent_path_object_key() -> None:
    client, _app = _client()
    payload = {
        "requestId": "req_ingestion_bad_0001",
        "operationId": "op_ingestion_bad_0001",
        "userId": "user_ingestion_0001",
        "documentId": "doc_ingestion_0001",
        "collection": "default",
        "objectKey": "../outside.pdf",
        "fileName": "outside.pdf",
        "mediaType": "application/pdf",
        "sizeBytes": 10,
        "sha256": "b" * 64,
    }

    response = client.post(
        "/internal/v1/ai/knowledge/ingestions",
        headers=_headers("req_ingestion_bad_0001", idempotency_key="idem_ingestion_bad_0001"),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


def test_internal_readiness_returns_503_when_real_collection_is_missing() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        internal_api={"service_token": TOKEN},
        rag_server={
            "query_mode": "real",
            "repo_path": ".",
            "collection": "missing_collection",
        },
    )
    client, app = _client(settings)
    app.state.rag_client = FakeRagServerClient()

    response = client.get("/internal/v1/health/readiness")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "NOT_READY"
    assert body["checks"]["rag"]["status"] == "DOWN"
    assert body["checks"]["rag"]["code"] == "COLLECTION_NOT_FOUND"
