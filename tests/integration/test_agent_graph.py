from __future__ import annotations

import asyncio

from backend.app.agent.graph import run_general_qa_graph
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_general_qa_graph_runs_supervisor_rag_verifier_safety_response() -> None:
    state = asyncio.run(
        run_general_qa_graph(
            "How should cattle feeding be managed?",
            rag_client=FakeRagServerClient(),
            session_id="s_general_graph",
        )
    )

    assert state.session_id == "s_general_graph"
    assert state.intent == "general_qa"
    assert state.evidence_status == "success"
    assert state.draft_answer is not None
    assert state.final_answer is not None
    assert "参考依据" in state.final_answer
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.tool_results["response_agent"]["sources"][0]["source_uri"].startswith("rag://")
    assert [item["node"] for item in state.agent_trace] == [
        "supervisor",
        "rag_agent",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]


def test_general_qa_graph_keeps_low_confidence_no_answer_safe() -> None:
    state = asyncio.run(
        run_general_qa_graph(
            "low confidence cattle answer",
            rag_client=FakeRagServerClient(),
            session_id="s_low_graph",
        )
    )

    assert state.evidence_status == "low_confidence"
    assert state.final_answer is not None
    assert "没有检索到足够依据" in state.final_answer
    assert state.tool_results["response_agent"]["sources"] == []
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
