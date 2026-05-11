from __future__ import annotations

from backend.app.model.answer_generator import AnswerGenerator
from backend.app.schemas.rag_server import RagCitation, RagSearchHit, RagSearchResult


def test_answer_generator_uses_only_rag_citations() -> None:
    result = RagSearchResult(
        query="犊牛腹泻怎么办",
        answer_text="应结合体温、精神状态和采食情况判断风险。",
        hits=[
            RagSearchHit(
                chunk_id="chunk_1",
                document_id="doc_1",
                document_title="犊牛腹泻防治技术手册",
                content="context",
                page=12,
                score=0.86,
            )
        ],
        citations=[
            RagCitation(
                source_id="doc_1",
                title="犊牛腹泻防治技术手册",
                page=12,
                section_title="常见病因",
                chunk_id="chunk_1",
            )
        ],
    )

    answer = AnswerGenerator().compose_with_citations(result)

    assert "应结合体温" in answer
    assert "参考依据" in answer
    assert "犊牛腹泻防治技术手册" in answer
    assert "P12" in answer
    assert "Unknown" not in answer


def test_answer_generator_does_not_invent_citations_on_empty_result() -> None:
    result = RagSearchResult(query="unknown", status="empty")

    answer = AnswerGenerator().compose_with_citations(result)

    assert "没有检索到足够依据" in answer
    assert "参考依据" not in answer

