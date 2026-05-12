from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _assert_response_contract(payload: dict) -> None:
    assert set(payload) == {"code", "message", "data", "request_id"}
    assert isinstance(payload["request_id"], str)


def test_list_rag_collections_returns_fake_collections() -> None:
    client = TestClient(create_app(settings=Settings(database={"url": "sqlite:///:memory:"})))

    response = client.get("/api/rag/collections")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["status"] == "success"
    assert payload["data"]["error_code"] is None
    assert [item["name"] for item in payload["data"]["collections"]] == ["default", "test"]
    assert set(payload["data"]["collections"][0]) == {"name", "description", "document_count", "updated_at"}


def test_list_rag_collections_real_mode_missing_path_does_not_fallback_to_fake() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        rag_server={"query_mode": "real", "repo_path": None, "collection": "livestock_knowledge"},
    )
    client = TestClient(create_app(settings=settings))

    response = client.get("/api/rag/collections")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 50002
    assert payload["data"]["collections"] == []
    assert payload["data"]["status"] == "error"
    assert payload["data"]["error_code"] == "RAG_SERVER_PATH_MISSING"


def test_get_rag_document_summary_requires_collection_path_and_returns_fake_summary() -> None:
    client = TestClient(create_app(settings=Settings(database={"url": "sqlite:///:memory:"})))

    response = client.get("/api/rag/collections/default/documents/doc_001/summary")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 0
    assert payload["data"]["doc_id"] == "doc_001"
    assert payload["data"]["collection"] == "default"
    assert payload["data"]["summary"]
    assert payload["data"]["tags"] == ["cattle", "calf", "diarrhea"]
    assert payload["data"]["source_uri_prefix"] == "rag://default/doc_001"
    assert payload["data"]["status"] == "success"
    assert payload["data"]["error_code"] is None


def test_get_rag_document_summary_legacy_path_without_collection_is_not_registered() -> None:
    client = TestClient(create_app(settings=Settings(database={"url": "sqlite:///:memory:"})))

    response = client.get("/api/rag/documents/doc_001/summary")

    assert response.status_code == 404


def test_get_rag_document_summary_real_mode_missing_path_does_not_fallback_to_fake() -> None:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        rag_server={"query_mode": "real", "repo_path": None, "collection": "livestock_knowledge"},
    )
    client = TestClient(create_app(settings=settings))

    response = client.get("/api/rag/collections/livestock_knowledge/documents/doc_001/summary")
    payload = response.json()

    assert response.status_code == 200
    _assert_response_contract(payload)
    assert payload["code"] == 50002
    assert payload["data"]["doc_id"] == "doc_001"
    assert payload["data"]["collection"] == "livestock_knowledge"
    assert payload["data"]["summary"] is None
    assert payload["data"]["status"] == "error"
    assert payload["data"]["error_code"] == "RAG_SERVER_PATH_MISSING"
