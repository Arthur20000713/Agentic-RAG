from __future__ import annotations

from backend.app.agent.state import MultiAgentState
from backend.app.agent.verifier_agent import VerifierAgent
from backend.app.schemas.agent import RetrievedContext


def test_verifier_agent_passes_supported_rag_answer() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="general_qa",
        evidence_status="success",
        draft_answer="根据资料，犊牛腹泻需要结合体温和精神状态评估。",
        retrieved_contexts=[
            RetrievedContext(
                chunk_id="chunk_1",
                document_id="doc_1",
                title="Manual",
                content="content",
                score=0.8,
            )
        ],
        tool_results={
            "livestock_rag_search": {
                "status": "success",
                "hits": [{"chunk_id": "chunk_1"}],
                "citations": [{"source_uri": "rag://default/doc_1/chunk_1", "title": "Manual"}],
                "mapping_warnings": [],
            }
        },
    )

    updated = VerifierAgent().verify(state)

    assert updated is state
    assert state.active_agent == "verifier_agent"
    assert state.verification_result == {
        "passed": True,
        "issues": [],
        "citation_issues": [],
        "unsupported_claims": [],
        "claim_checks": [
            {
                "claim": state.draft_answer,
                "source_uri": "rag://default/doc_1/chunk_1",
                "supported": True,
                "issue": None,
            }
        ],
    }
    assert state.errors == []
    assert state.agent_trace[-1]["node"] == "verifier_agent"
    assert state.agent_trace[-1]["status"] == "success"


def test_verifier_agent_detects_missing_citation_issue() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="general_qa",
        evidence_status="success",
        draft_answer="犊牛腹泻可能与病原感染有关，应隔离观察。",
        retrieved_contexts=[
            RetrievedContext(
                chunk_id="chunk_1",
                document_id="doc_1",
                title="Manual",
                content="content",
                score=0.8,
            )
        ],
        tool_results={
            "livestock_rag_search": {
                "status": "success",
                "hits": [{"chunk_id": "chunk_1"}],
                "citations": [],
                "mapping_warnings": [],
            }
        },
    )

    VerifierAgent().verify(state)

    assert state.verification_result is not None
    assert state.verification_result["passed"] is False
    assert state.verification_result["citation_issues"] == ["missing_citation"]
    assert "missing_citation" in state.verification_result["issues"]
    assert state.verification_result["claim_checks"][0]["source_uri"] is None
    assert state.verification_result["claim_checks"][0]["supported"] is False
    assert state.verification_result["claim_checks"][0]["issue"] == "claim_missing_source_uri"
    assert state.errors[-1].tool_name == "verifier_agent"
    assert state.agent_trace[-1]["status"] == "failed"


def test_verifier_agent_detects_unsupported_claim_on_low_confidence_evidence() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="general_qa",
        evidence_status="low_confidence",
        draft_answer="犊牛腹泻需要立即隔离处理。",
        tool_results={
            "livestock_rag_search": {
                "status": "low_confidence",
                "hits": [],
                "citations": [],
                "mapping_warnings": [],
            }
        },
    )

    VerifierAgent().verify(state)

    assert state.verification_result is not None
    assert state.verification_result["passed"] is False
    assert state.verification_result["unsupported_claims"] == ["unsupported_claim"]
    assert "unsupported_claim" in state.verification_result["issues"]
    assert any(error.error_code == "unsupported_claim" for error in state.errors)


def test_verifier_agent_uses_measurement_evidence_boundary() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="body measurement",
        intent="measurement_analysis",
        draft_answer="胸围增长偏慢。",
        measurement_report={
            "abnormal_items": ["chest_girth_cm"],
            "evidence": [],
        },
    )

    VerifierAgent().verify(state)

    assert state.verification_result is not None
    assert state.verification_result["passed"] is False
    assert "measurement_missing_evidence" in state.verification_result["issues"]
    assert "livestock_rag_search" not in state.tool_results
