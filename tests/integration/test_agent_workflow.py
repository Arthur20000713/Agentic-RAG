from __future__ import annotations

import asyncio

from backend.app.agent.workflow import run_disease_consultation, run_general_qa
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.schemas.rag_server import RagCitation, RagSearchHit, RagSearchResult


class AlwaysRelevantRagClient(FakeRagServerClient):
    async def query(
        self,
        query: str,
        *,
        top_k: int = 4,
        collection: str | None = None,
        domain: str | None = None,
        species: str | None = None,
        request_id: str | None = None,
    ) -> RagSearchResult:
        return RagSearchResult(
            query=query,
            status="success",
            hits=[
                RagSearchHit(
                    rank=1,
                    chunk_id="chunk_1",
                    document_id="doc_1",
                    document_title="Doc",
                    content="retrieved content",
                    source_uri="rag://livestock_v4_2/doc_1/chunk_1",
                    score=0.9,
                )
            ],
            citations=[
                RagCitation(
                    source_id="doc_1",
                    source_uri="rag://livestock_v4_2/doc_1/chunk_1",
                    title="Doc",
                    chunk_id="chunk_1",
                )
            ],
        )


def test_general_qa_workflow_uses_fake_rag_and_citations() -> None:
    state = asyncio.run(
        run_general_qa(
            "犊牛腹泻的常见原因是什么？",
            rag_client=FakeRagServerClient(),
            session_id="s_general",
        )
    )

    assert state.intent == "general_qa"
    assert state.final_answer is not None
    assert "参考依据" in state.final_answer
    assert state.retrieved_contexts
    assert "livestock_rag_search" in state.tool_results


def test_general_qa_policy_no_answer_keeps_rag_observable_without_contexts() -> None:
    state = asyncio.run(
        run_general_qa(
            "What does this cattle corpus say about pet cat vaccination schedules?",
            rag_client=AlwaysRelevantRagClient(),
            session_id="s_no_answer_policy",
        )
    )

    assert "livestock_rag_search" in state.tool_results
    assert "rag_answer_policy" in state.tool_results
    assert state.retrieved_contexts == []
    assert state.final_answer is not None
    assert "没有检索到足够依据" in state.final_answer
    assert "[1]" not in state.final_answer


def test_disease_high_risk_policy_calls_rag_before_safety_refusal() -> None:
    state = asyncio.run(
        run_disease_consultation(
            "犊牛腹泻两天，请直接告诉我庆大霉素每公斤打多少毫克。",
            rag_client=AlwaysRelevantRagClient(),
            session_id="s_safety_policy",
        )
    )

    assert "livestock_rag_search" in state.tool_results
    assert "safety_precheck" in state.tool_results
    assert state.need_follow_up is False
    assert state.final_answer is not None
    assert "安全提示" in state.final_answer
