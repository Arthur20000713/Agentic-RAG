from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.graph import run_general_qa_graph
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.schemas.rag_server import RagSearchHit, RagSearchResult


class ScriptedPrimaryLLM:
    def __init__(
        self,
        *,
        queries: list[dict[str, str]],
        rewrite: dict[str, str] | None = None,
    ) -> None:
        self.queries = queries
        self.rewrite = rewrite
        self.schema_names: list[str] = []

    async def generate_json(self, request: Any) -> dict[str, Any]:
        self.schema_names.append(request.schema_name)
        if request.schema_name == "task_plan":
            return {
                "status": "error",
                "fallback_required": True,
                "reason": "use deterministic system-test plan",
            }
        if request.schema_name == "retrieval_decomposition":
            return {"status": "success", "queries": self.queries}
        if request.schema_name == "retrieval_rewrite":
            if self.rewrite is None:
                raise AssertionError("unexpected retrieval rewrite")
            return {"status": "success", **self.rewrite}
        if request.schema_name == "grounded_rag_answer":
            return {
                "status": "success",
                "schema_name": "grounded_rag_answer",
                "answer_draft": "The calf feeding, water, and housing evidence is available [1].",
                "evidence_sufficient": True,
                "fallback_required": False,
            }
        if request.schema_name == "reference_only_answer":
            raise AssertionError("agentic insufficient must not use reference-only answering")
        raise AssertionError(f"unexpected schema: {request.schema_name}")


class ScriptedRagClient(FakeRagServerClient):
    def __init__(self, responses: dict[str, RagSearchResult]) -> None:
        super().__init__()
        self.responses = responses
        self.queries: list[str] = []

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.queries.append(query)
        return self.responses[query].model_copy(deep=True)


def _settings() -> Settings:
    return Settings(
        primary_llm={
            "enabled": True,
            "provider": "mock",
            "model": "agentic-system-test",
            "base_url": "mock",
        }
    )


def _hit(
    query: str,
    chunk_id: str,
    *,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> RagSearchResult:
    return RagSearchResult(
        query=query,
        status="success",
        hits=[
            RagSearchHit(
                chunk_id=chunk_id,
                document_id=f"doc_{chunk_id}",
                document_title=f"Guide {chunk_id}",
                content=content,
                source_uri=f"rag://livestock/doc_{chunk_id}",
                score=0.9,
                metadata=metadata or {},
            )
        ],
    )


def _empty(query: str) -> RagSearchResult:
    return RagSearchResult(query=query, status="empty")


def test_full_graph_decomposes_two_queries_and_returns_grounded_sources() -> None:
    feed_query = "How should calf feeding be managed?"
    water_query = "How should calf water be managed?"
    model = ScriptedPrimaryLLM(
        queries=[
            {"text": feed_query, "purpose": "feeding"},
            {"text": water_query, "purpose": "water"},
        ]
    )
    rag = ScriptedRagClient(
        {
            feed_query: _hit(
                feed_query,
                "feed",
                content="Calf feeding evidence supports a stable ration.",
            ),
            water_query: _hit(
                water_query,
                "water",
                content="Calf water evidence supports clean water access.",
            ),
        }
    )

    state = asyncio.run(
        run_general_qa_graph(
            "How should calf feeding and water be managed?",
            rag_client=rag,
            settings=_settings(),
            primary_llm_client=model,
            session_id="agentic_system_decompose",
        )
    )

    assert rag.queries == [feed_query, water_query]
    assert state.agentic_retrieval is not None
    assert state.agentic_retrieval.decomposition_source == "model"
    assert state.agentic_retrieval.rag_call_count == 2
    assert state.agentic_retrieval.secondary_retrieval_count == 0
    assert state.agentic_retrieval.final_status == "sufficient"
    assert state.tool_results["response_agent"]["sources"]
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True


def test_full_graph_bounds_three_primary_queries_plus_one_secondary() -> None:
    primary_queries = [
        "How should calf feeding be managed?",
        "How should calf water be managed?",
        "How should calf housing be managed?",
    ]
    secondary_query = (
        "How should calf feeding, water, and housing be managed? missing evidence"
    )
    model = ScriptedPrimaryLLM(
        queries=[
            {"text": primary_queries[0], "purpose": "feeding"},
            {"text": primary_queries[1], "purpose": "water"},
            {"text": primary_queries[2], "purpose": "housing"},
        ],
        rewrite={"query": secondary_query, "purpose": "fill all evidence gaps"},
    )
    rag = ScriptedRagClient(
        {
            **{query: _empty(query) for query in primary_queries},
            secondary_query: _hit(
                secondary_query,
                "complete",
                content="Calf feeding water housing evidence is available.",
            ),
        }
    )

    state = asyncio.run(
        run_general_qa_graph(
            "How should calf feeding, water, and housing be managed?",
            rag_client=rag,
            settings=_settings(),
            primary_llm_client=model,
            session_id="agentic_system_secondary",
        )
    )

    assert rag.queries == [*primary_queries, secondary_query]
    assert state.agentic_retrieval is not None
    assert state.agentic_retrieval.rag_call_count == 4
    assert state.agentic_retrieval.secondary_retrieval_count == 1
    assert state.agentic_retrieval.rewrite_source == "model"
    assert [grade.round for grade in state.agentic_retrieval.grades] == [1, 2]
    assert state.agentic_retrieval.final_status == "sufficient"
    assert state.tool_results["response_agent"]["sources"]


def test_full_graph_returns_no_answer_when_conflict_survives_secondary() -> None:
    original_query = "What daily water allowance should a calf receive?"
    secondary_query = f"{original_query} compare source evidence"
    model = ScriptedPrimaryLLM(
        queries=[{"text": original_query, "purpose": "daily water allowance"}],
        rewrite={"query": secondary_query, "purpose": "resolve source conflict"},
    )
    first = _hit(
        original_query,
        "water_10",
        content="One source states a daily water allowance.",
        metadata={"claim_topic": "daily water allowance", "claim_value": "10 L"},
    )
    first.hits.append(
        _hit(
            original_query,
            "water_20",
            content="Another source states a different daily water allowance.",
            metadata={"claim_topic": "daily water allowance", "claim_value": "20 L"},
        ).hits[0]
    )
    rag = ScriptedRagClient(
        {
            original_query: first,
            secondary_query: _hit(
                secondary_query,
                "water_review",
                content="The reviewed sources do not resolve the conflict.",
            ),
        }
    )

    state = asyncio.run(
        run_general_qa_graph(
            original_query,
            rag_client=rag,
            settings=_settings(),
            primary_llm_client=model,
            session_id="agentic_system_conflict",
        )
    )

    assert rag.queries == [original_query, secondary_query]
    assert state.agentic_retrieval is not None
    assert state.agentic_retrieval.rag_call_count == 2
    assert state.agentic_retrieval.final_status == "insufficient"
    assert state.agentic_retrieval.grades[-1].conflicts
    assert "reference_only_answer" not in model.schema_names
    assert "unresolved conflicts" in state.final_answer
    assert state.tool_results["livestock_rag_search"]["hits"] == []
    assert state.tool_results["livestock_rag_search"]["citations"] == []
    assert state.tool_results["response_agent"]["sources"] == []
    assert state.replan_count == 0
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
