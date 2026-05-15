from __future__ import annotations

from backend.app.integrations.rag_server.mapper import (
    PARTIAL_SOURCE_URI_WARNING,
    SYNTHESIZED_CITATION_WARNING,
    RagServerMapper,
    build_source_uri,
)


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
    assert SYNTHESIZED_CITATION_WARNING in result.mapping_warnings


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


def test_build_source_uri_uses_collection_doc_and_chunk() -> None:
    source_uri = build_source_uri("livestock_knowledge", "doc_001", "chunk_012")

    assert source_uri == "rag://livestock_knowledge/doc_001/chunk_012"


def test_build_source_uri_generates_stable_fallback_parts() -> None:
    first = build_source_uri(
        "livestock_knowledge",
        None,
        None,
        title="犊牛腹泻防治技术手册",
        content="犊牛腹泻常见原因包括饲养管理变化。",
        page=12,
        rank=1,
    )
    second = build_source_uri(
        "livestock_knowledge",
        None,
        None,
        title="犊牛腹泻防治技术手册",
        content="犊牛腹泻常见原因包括饲养管理变化。",
        page=12,
        rank=1,
    )

    assert first == second
    assert first.startswith("rag://livestock_knowledge/unknown-doc-")
    assert "/unknown-chunk-" in first


def test_mapper_populates_source_uri_without_warning_when_ids_exist() -> None:
    result = RagServerMapper.to_search_result(
        {
            "query": "q",
            "collection": "livestock_knowledge",
            "hits": [
                {
                    "doc_id": "doc_001",
                    "chunk_id": "chunk_012",
                    "title": "Doc",
                    "content": "content",
                    "score": 0.7,
                }
            ],
        }
    )

    assert result.hits[0].source_uri == "rag://livestock_knowledge/doc_001/chunk_012"
    assert result.citations[0].source_uri == "rag://livestock_knowledge/doc_001/chunk_012"
    assert PARTIAL_SOURCE_URI_WARNING not in result.mapping_warnings
    assert SYNTHESIZED_CITATION_WARNING in result.mapping_warnings


def test_mapper_records_warning_for_fallback_source_uri() -> None:
    result = RagServerMapper.to_search_result(
        {
            "query": "q",
            "collection": "livestock_knowledge",
            "hits": [
                {
                    "title": "Doc",
                    "content": "content",
                    "score": 0.7,
                }
            ],
        }
    )

    assert result.hits[0].source_uri is not None
    assert result.hits[0].source_uri.startswith("rag://livestock_knowledge/unknown-doc-")
    assert str(result.hits[0].document_id).startswith("unknown-doc-")
    assert result.hits[0].chunk_id.startswith("unknown-chunk-")
    assert PARTIAL_SOURCE_URI_WARNING in result.mapping_warnings
    assert SYNTHESIZED_CITATION_WARNING not in result.mapping_warnings
    assert result.citations == []
