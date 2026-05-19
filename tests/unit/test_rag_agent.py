from __future__ import annotations

import asyncio

from backend.app.agent.rag_agent import RagAgent
from backend.app.agent.state import MultiAgentState
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_rag_agent_success_attaches_contexts_and_trace() -> None:
    state = MultiAgentState(session_id="s1", user_query="calf diarrhea")

    updated = asyncio.run(RagAgent(FakeRagServerClient()).run(state))

    assert updated is state
    assert state.active_agent == "rag_agent"
    assert state.rag_query == "calf diarrhea"
    assert state.evidence_status == "success"
    assert state.tool_results["livestock_rag_search"]["status"] == "success"
    assert [context.chunk_id for context in state.retrieved_contexts] == [
        "doc_001_chunk_012",
        "doc_002_chunk_004",
    ]
    assert state.agent_trace[-1]["node"] == "rag_agent"
    assert state.agent_trace[-1]["status"] == "success"
    assert state.agent_trace[-1]["result_count"] == 2


def test_rag_agent_low_confidence_sets_evidence_status() -> None:
    state = MultiAgentState(session_id="s1", user_query="low confidence cattle answer")

    asyncio.run(RagAgent(FakeRagServerClient()).run(state))

    assert state.evidence_status == "low_confidence"
    assert state.tool_results["livestock_rag_search"]["status"] == "low_confidence"
    assert state.retrieved_contexts == []
    assert state.errors == []
    assert state.agent_trace[-1]["evidence_status"] == "low_confidence"


def test_rag_agent_error_records_tool_error_without_contexts() -> None:
    state = MultiAgentState(session_id="s1", user_query="error")

    asyncio.run(RagAgent(FakeRagServerClient()).run(state))

    assert state.evidence_status == "error"
    assert state.retrieved_contexts == []
    assert state.errors[0].tool_name == "rag_agent"
    assert state.errors[0].error_code == "RAG_INTERNAL_ERROR"
    assert state.agent_trace[-1]["status"] == "error"
    assert state.agent_trace[-1]["error_code"] == "RAG_INTERNAL_ERROR"


def test_rag_agent_prefers_existing_rag_query() -> None:
    state = MultiAgentState(session_id="s1", user_query="calf diarrhea", rag_query="empty")

    asyncio.run(RagAgent(FakeRagServerClient()).run(state))

    assert state.rag_query == "empty"
    assert state.tool_results["livestock_rag_search"]["query"] == "empty"
    assert state.evidence_status == "empty"
