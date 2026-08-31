from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.agent.state import MultiAgentState
from backend.app.schemas.agent import AgentToolError, RetrievedContext


def test_multi_agent_state_has_contract_fields_and_defaults() -> None:
    state = MultiAgentState(session_id="s1", user_query="calf diarrhea")

    assert state.normalized_query is None
    assert state.intent is None
    assert state.route_reason is None
    assert state.active_agent is None
    assert state.session_context == {}
    assert state.extracted_slots == {}
    assert state.rag_query is None
    assert state.retrieved_contexts == []
    assert state.evidence_status is None
    assert state.agentic_retrieval is None
    assert state.disease_assessment is None
    assert state.measurement_report is None
    assert state.draft_answer is None
    assert state.verification_result is None
    assert state.safety_result is None
    assert state.final_answer is None
    assert state.tool_results == {}
    assert state.errors == []
    assert state.agent_trace == []


def test_multi_agent_state_default_collections_are_isolated() -> None:
    first = MultiAgentState(session_id="s1", user_query="q1")
    second = MultiAgentState(session_id="s2", user_query="q2")

    first.session_context["species"] = "cattle"
    first.agent_trace.append({"node": "supervisor", "status": "success"})

    assert second.session_context == {}
    assert second.agent_trace == []


def test_multi_agent_state_accepts_reused_v1_schema_types() -> None:
    context = RetrievedContext(
        chunk_id="chunk_1",
        document_id="doc_1",
        title="Manual",
        content="content",
        score=0.82,
    )
    error = AgentToolError(tool_name="rag_agent", error_code="RAG_TIMEOUT", message="timeout")

    state = MultiAgentState(
        session_id="s1",
        user_query="q",
        intent="general_qa",
        evidence_status="success",
        retrieved_contexts=[context],
        errors=[error],
        agent_trace=[{"node": "rag_agent", "status": "success", "latency_ms": 12}],
    )

    assert state.retrieved_contexts[0].chunk_id == "chunk_1"
    assert state.errors[0].error_code == "RAG_TIMEOUT"
    assert state.agent_trace[0]["node"] == "rag_agent"


def test_multi_agent_state_rejects_unknown_intent_and_evidence_status() -> None:
    with pytest.raises(ValidationError):
        MultiAgentState(session_id="s1", user_query="q", intent="unknown")

    with pytest.raises(ValidationError):
        MultiAgentState(session_id="s1", user_query="q", evidence_status="unsupported")
