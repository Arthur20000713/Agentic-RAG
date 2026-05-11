from __future__ import annotations

from backend.app.integrations.rag_server.mapper import RagServerMapper


def test_mapper_builds_citations_from_hits_when_missing() -> None:
    payload = {
        "query": "q",
        "hits": [
            {
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "document_title": "Doc",
                "content": "content",
                "page": 3,
                "section_title": "Section",
                "score": 0.7,
            }
        ],
    }

    result = RagServerMapper.to_search_result(payload)

    assert result.status == "success"
    assert result.hits[0].chunk_id == "chunk_1"
    assert result.citations[0].title == "Doc"
    assert result.citations[0].page == 3


def test_mapper_preserves_error_without_hits() -> None:
    result = RagServerMapper.to_search_result(
        {
            "isError": True,
            "query": "q",
            "error_code": "RAG_TIMEOUT",
            "error_message": "timeout",
        }
    )

    assert result.status == "error"
    assert result.error_code == "RAG_TIMEOUT"
    assert result.hits == []

