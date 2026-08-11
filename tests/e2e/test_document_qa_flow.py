from __future__ import annotations

import asyncio

from backend.app.agent.graph import run_general_qa_graph
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_document_qa_flow_fake_result_has_citations() -> None:
    state = asyncio.run(
        run_general_qa_graph(
            "How should calf feeding management be handled after weaning?",
            rag_client=FakeRagServerClient(),
            session_id="s_document_qa",
        )
    )

    rag_result = state.tool_results["livestock_rag_search"]

    assert state.intent == "general_qa"
    assert state.final_answer
    assert "[1]" in state.final_answer
    assert state.retrieved_contexts
    assert rag_result["status"] == "success"
    assert rag_result["hits"][0]["chunk_id"] == "doc_001_chunk_012"
    assert rag_result["citations"][0]["source_id"] == "doc_001"
    assert state.errors == []


def test_document_qa_flow_empty_result_does_not_fabricate_citations() -> None:
    state = asyncio.run(
        run_general_qa_graph(
            "empty knowledge-base question",
            rag_client=FakeRagServerClient(),
            session_id="s_document_qa_empty",
        )
    )

    rag_result = state.tool_results["livestock_rag_search"]

    assert state.intent == "general_qa"
    assert state.final_answer
    assert "[1]" not in state.final_answer
    assert state.retrieved_contexts == []
    assert rag_result["status"] == "empty"
    assert rag_result["hits"] == []
    assert rag_result["citations"] == []
    assert state.errors == []
