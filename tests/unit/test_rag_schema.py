from __future__ import annotations

from backend.app.integrations.rag_server.schema import StandardRetrievedContext
from backend.app.schemas.rag_server import RagCitation, RagSearchResult


def test_standard_retrieved_context_contains_v2_source_and_score_fields() -> None:
    context = StandardRetrievedContext(
        rank=1,
        collection="livestock_knowledge",
        chunk_id="chunk_012",
        document_id="doc_001",
        document_title="犊牛腹泻防治技术手册",
        content="犊牛腹泻常见原因包括饲养管理变化。",
        source_uri="rag://livestock_knowledge/doc_001/chunk_012",
        score=0.82,
        score_type="rag_server_score",
        raw_score=0.82,
        mapped_score=0.82,
    )

    payload = context.model_dump()

    assert payload["source_uri"] == "rag://livestock_knowledge/doc_001/chunk_012"
    assert payload["score_type"] == "rag_server_score"
    assert payload["raw_score"] == 0.82
    assert payload["mapped_score"] == 0.82


def test_rag_search_result_contains_raw_response_id_and_mapping_warnings() -> None:
    result = RagSearchResult(
        query="犊牛腹泻怎么办",
        hits=[],
        raw_response_id="rag_trace_001",
        mapping_warnings=["RAG_MAPPING_TEXT_ONLY_RESPONSE"],
    )

    payload = result.model_dump()

    assert payload["raw_response_id"] == "rag_trace_001"
    assert payload["mapping_warnings"] == ["RAG_MAPPING_TEXT_ONLY_RESPONSE"]


def test_citation_can_bind_to_source_uri() -> None:
    citation = RagCitation(
        source_id="doc_001",
        source_uri="rag://livestock_knowledge/doc_001/chunk_012",
        title="犊牛腹泻防治技术手册",
        chunk_id="chunk_012",
    )

    assert citation.source_uri == "rag://livestock_knowledge/doc_001/chunk_012"
