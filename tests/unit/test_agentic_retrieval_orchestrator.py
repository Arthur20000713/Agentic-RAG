from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.agentic_retrieval import AgenticRetrievalOrchestrator
from backend.app.agent.retrieval_query_strategy import (
    DecompositionOutcome,
    RewriteOutcome,
)
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.rag_server import (
    RagDocumentSummary,
    RagSearchHit,
    RagSearchResult,
)
from backend.app.schemas.retrieval import RetrievalQuery


class StubDecomposer:
    def __init__(self, queries: list[RetrievalQuery]) -> None:
        self.queries = queries

    async def decompose(self, original_query: str) -> DecompositionOutcome:
        return DecompositionOutcome(
            queries=self.queries,
            source="test",
            fallback_used=False,
        )


class StubRewriter:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.calls: list[dict[str, Any]] = []

    async def rewrite(self, **kwargs: Any) -> RewriteOutcome:
        self.calls.append(kwargs)
        if self.reject:
            return RewriteOutcome(
                query=None,
                source="rejected",
                fallback_used=False,
                rejection_reasons=["semantic_constraint_violation"],
            )
        parents = [query_id for query_id, _ in kwargs["previous_queries"]]
        return RewriteOutcome(
            query=RetrievalQuery(
                query_id="q_secondary",
                text=f"{kwargs['original_query']} secondary evidence",
                origin="secondary",
                purpose="fill evidence gap",
                parent_query_ids=parents,
            ),
            source="test",
            fallback_used=False,
        )


class ScriptedRagClient(RagServerClient):
    def __init__(self, responses: dict[str, RagSearchResult | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.calls.append({"query": query, **kwargs})
        response = self.responses[query]
        if isinstance(response, Exception):
            raise response
        return response.model_copy(deep=True)

    async def get_document_summary(
        self,
        doc_id: str,
        *,
        collection: str | None = None,
    ) -> RagDocumentSummary:
        raise AssertionError("agentic retrieval must grade original hit content")

    async def list_collections(self, *, include_stats: bool = True) -> list[str]:
        return []


def _query(index: int, purpose: str) -> RetrievalQuery:
    return RetrievalQuery(
        query_id=f"q_primary_{index}",
        text=f"query {index}",
        origin="original" if index == 1 else "decomposed",
        purpose=purpose,
    )


def _result(query: str, chunk_id: str, *, score: float = 0.9) -> RagSearchResult:
    return RagSearchResult(
        query=query,
        status="success",
        hits=[
            RagSearchHit(
                chunk_id=chunk_id,
                document_id=f"doc_{chunk_id}",
                document_title=f"Guide {chunk_id}",
                content=f"Original evidence {chunk_id}",
                source_uri=f"rag://kb/doc_{chunk_id}",
                score=score,
            )
        ],
    )


def _empty(query: str) -> RagSearchResult:
    return RagSearchResult(query=query, status="empty")


def _run(
    client: ScriptedRagClient,
    queries: list[RetrievalQuery],
    *,
    rewriter: StubRewriter | None = None,
):
    return asyncio.run(
        AgenticRetrievalOrchestrator(
            client,
            decomposer=StubDecomposer(queries),
            rewrite_guard=rewriter or StubRewriter(),
        ).run(
            original_query="trusted calf question",
            query_source="normalized_query",
            request_id="request_1",
            operation_prefix="request_1:plan_1:retrieve",
        )
    )


def test_orchestrator_returns_sufficient_canonical_result_in_one_call() -> None:
    queries = [_query(1, "feeding")]
    client = ScriptedRagClient({"query 1": _result("query 1", "feed")})

    outcome = _run(client, queries)

    assert outcome.result.status == "success"
    assert [hit.chunk_id for hit in outcome.result.hits] == ["feed"]
    assert [citation.chunk_id for citation in outcome.result.citations] == ["feed"]
    assert outcome.state.final_status == "sufficient"
    assert outcome.state.rag_call_count == 1
    assert outcome.state.decomposition_source == "test"
    assert outcome.state.rewrite_source is None
    assert outcome.state.attempts[0].operation_key.endswith(":r1:q_primary_1")


def test_orchestrator_uses_the_configured_real_rag_score_scale() -> None:
    queries = [_query(1, "health")]
    client = ScriptedRagClient(
        {"query 1": _result("query 1", "health", score=0.0328)}
    )

    outcome = _run(client, queries)

    assert outcome.result.status == "success"
    assert outcome.state.grades[0].relevance == 0.0328
    assert outcome.state.rag_call_count == 1


def test_orchestrator_aggregates_two_primary_queries_without_secondary() -> None:
    queries = [_query(1, "feeding"), _query(2, "water")]
    client = ScriptedRagClient(
        {
            "query 1": _result("query 1", "feed"),
            "query 2": _result("query 2", "water"),
        }
    )

    outcome = _run(client, queries)

    assert outcome.result.status == "success"
    assert [hit.chunk_id for hit in outcome.result.hits] == ["feed", "water"]
    assert outcome.state.rag_call_count == 2
    assert outcome.state.secondary_retrieval_count == 0


def test_orchestrator_caps_three_primary_plus_one_secondary_call() -> None:
    queries = [_query(1, "feeding"), _query(2, "water"), _query(3, "housing")]
    secondary_text = "trusted calf question secondary evidence"
    client = ScriptedRagClient(
        {
            "query 1": _empty("query 1"),
            "query 2": _empty("query 2"),
            "query 3": _empty("query 3"),
            secondary_text: _result(secondary_text, "complete"),
        }
    )

    outcome = _run(client, queries)

    assert outcome.result.status == "success"
    assert outcome.state.rag_call_count == 4
    assert outcome.state.secondary_retrieval_count == 1
    assert len(client.calls) == 4
    assert outcome.state.grades[-1].round == 2


def test_orchestrator_returns_no_answer_without_residual_hits_after_second_round() -> None:
    queries = [_query(1, "feeding"), _query(2, "water"), _query(3, "housing")]
    secondary_text = "trusted calf question secondary evidence"
    client = ScriptedRagClient(
        {
            "query 1": _empty("query 1"),
            "query 2": _empty("query 2"),
            "query 3": _empty("query 3"),
            secondary_text: _empty(secondary_text),
        }
    )

    outcome = _run(client, queries)

    assert outcome.result.status == "low_confidence"
    assert outcome.result.hits == []
    assert outcome.result.citations == []
    assert outcome.state.final_status == "insufficient"
    assert outcome.state.rag_call_count == 4
    assert outcome.infrastructure_failed is False


def test_orchestrator_allows_partial_failure_to_be_filled_by_secondary() -> None:
    queries = [_query(1, "feeding"), _query(2, "water")]
    secondary_text = "trusted calf question secondary evidence"
    client = ScriptedRagClient(
        {
            "query 1": _result("query 1", "feed"),
            "query 2": TimeoutError("rag timeout"),
            secondary_text: _result(secondary_text, "water"),
        }
    )

    outcome = _run(client, queries)

    assert outcome.result.status == "success"
    assert outcome.state.rag_call_count == 3
    assert [attempt.status for attempt in outcome.state.attempts] == [
        "success",
        "error",
        "success",
    ]
    assert outcome.infrastructure_failed is False


def test_orchestrator_returns_infrastructure_error_when_all_primary_calls_fail() -> None:
    queries = [_query(1, "feeding"), _query(2, "water")]
    rewriter = StubRewriter()
    client = ScriptedRagClient(
        {
            "query 1": TimeoutError("first timeout"),
            "query 2": RuntimeError("second failure"),
        }
    )

    outcome = _run(client, queries, rewriter=rewriter)

    assert outcome.result.status == "error"
    assert outcome.result.error_code == "RAG_ALL_QUERIES_FAILED"
    assert outcome.state.final_status == "error"
    assert outcome.infrastructure_failed is True
    assert outcome.state.rag_call_count == 2
    assert rewriter.calls == []


def test_orchestrator_stops_without_secondary_call_when_rewrite_is_rejected() -> None:
    queries = [_query(1, "feeding")]
    rewriter = StubRewriter(reject=True)
    client = ScriptedRagClient({"query 1": _empty("query 1")})

    outcome = _run(client, queries, rewriter=rewriter)

    assert outcome.result.status == "low_confidence"
    assert outcome.state.final_status == "insufficient"
    assert outcome.state.termination_code == "REWRITE_REJECTED"
    assert outcome.state.rag_call_count == 1
    assert len(client.calls) == 1
