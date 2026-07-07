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


def test_answer_generator_synthesizes_answer_when_rag_server_returns_result_dump() -> None:
    result = RagSearchResult(
        query="断奶犊牛如何饲喂",
        answer_text=(
            "## Query Results\n\n"
            "### Result 1\n"
            "Score: 0.87\n"
            "断奶后应保持日粮稳定，并逐步提高开食料采食量。"
        ),
        hits=[
            RagSearchHit(
                chunk_id="chunk_1",
                document_id="doc_1",
                document_title="犊牛断奶饲养指南",
                content="断奶后应保持日粮稳定，并逐步提高开食料采食量。需要保证清洁饮水和充足干草。",
                source_uri="rag://livestock_v4_2/doc_1/chunk_1",
                page=8,
                score=0.87,
            )
        ],
        citations=[
            RagCitation(
                source_id="doc_1",
                source_uri="rag://livestock_v4_2/doc_1/chunk_1",
                title="犊牛断奶饲养指南",
                page=8,
                chunk_id="chunk_1",
            )
        ],
    )

    answer = AnswerGenerator().compose_with_citations(result)

    assert "## Query Results" not in answer
    assert "### Result" not in answer
    assert "Score:" not in answer
    assert "断奶后应保持日粮稳定" in answer
    assert "参考依据" in answer
    assert "rag://livestock_v4_2/doc_1/chunk_1" in answer
