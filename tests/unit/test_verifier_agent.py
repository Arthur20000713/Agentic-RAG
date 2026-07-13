from __future__ import annotations

from backend.app.agent.rag_answer_policy import NO_ANSWER_TEXT
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

    state.draft_answer = f"{state.draft_answer} [1]"
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
        "disease_reasoning_issues": [],
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


def test_verifier_agent_rejects_disease_reasoning_refs_outside_evidence_gate() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="disease_consultation",
        evidence_status="success",
        draft_answer="Evidence-based draft.",
        tool_results={
            "disease_evidence_gate": {
                "allowed": True,
                "evidence_refs": [{"source_uri": "rag://livestock/doc/chunk_1", "chunk_id": "chunk_1"}],
            },
            "disease_reasoning_shadow": {
                "status": "success",
                "reasoning": {
                    "contributing_factors": [
                        {
                            "text": "Digestive disturbance may be relevant.",
                            "evidence_refs": [{"source_uri": "rag://livestock/doc/chunk_2", "chunk_id": "chunk_2"}],
                        }
                    ],
                    "safe_actions": [],
                    "vet_triggers": [],
                    "uncertainties": [],
                    "not_diagnosis_notice": "This is not a diagnosis.",
                },
            },
            "livestock_rag_search": {
                "status": "success",
                "hits": [{"chunk_id": "chunk_1", "source_uri": "rag://livestock/doc/chunk_1"}],
                "citations": [
                    {"title": "guide", "source_uri": "rag://livestock/doc/chunk_1", "chunk_id": "chunk_1"}
                ],
                "mapping_warnings": [],
            },
        },
    )

    VerifierAgent().verify(state)

    assert state.verification_result is not None
    assert state.verification_result["passed"] is False
    assert "disease_reasoning_ref_outside_gate" in state.verification_result["disease_reasoning_issues"]
    assert "disease_reasoning_ref_outside_gate" in state.verification_result["issues"]


def test_verifier_agent_rejects_disease_reasoning_safety_redlines() -> None:
    ref = {"source_uri": "rag://livestock/doc/chunk_1", "chunk_id": "chunk_1"}
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="disease_consultation",
        evidence_status="success",
        draft_answer="Evidence-based draft.",
        tool_results={
            "disease_evidence_gate": {"allowed": True, "evidence_refs": [ref]},
            "disease_reasoning_shadow": {
                "status": "success",
                "reasoning": {
                    "contributing_factors": [{"text": "This is a definitive diagnosis of pneumonia.", "evidence_refs": [ref]}],
                    "safe_actions": [{"text": "Give oxytetracycline 5 mg/kg now.", "evidence_refs": [ref]}],
                    "vet_triggers": [],
                    "uncertainties": [],
                    "not_diagnosis_notice": "This is not a diagnosis.",
                },
            },
            "livestock_rag_search": {
                "status": "success",
                "hits": [{"chunk_id": "chunk_1", "source_uri": "rag://livestock/doc/chunk_1"}],
                "citations": [{"title": "guide", "source_uri": "rag://livestock/doc/chunk_1", "chunk_id": "chunk_1"}],
                "mapping_warnings": [],
            },
        },
    )

    VerifierAgent().verify(state)

    assert state.verification_result is not None
    assert state.verification_result["passed"] is False
    assert "disease_reasoning_safety_violation" in state.verification_result["disease_reasoning_issues"]
    assert "disease_reasoning_safety_violation" in state.verification_result["issues"]


def test_verifier_agent_fails_closed_on_unsupported_english_claim() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="How should calves be managed after weaning?",
        intent="general_qa",
        evidence_status="success",
        draft_answer="Calves can fly after weaning [1].",
        retrieved_contexts=[
            RetrievedContext(
                chunk_id="chunk_1",
                document_id="doc_1",
                title="Water guide",
                content="Provide clean water every day.",
                score=0.8,
            )
        ],
        tool_results={
            "livestock_rag_search": {
                "status": "success",
                "hits": [
                    {
                        "chunk_id": "chunk_1",
                        "content": "Provide clean water every day.",
                        "source_uri": "rag://default/doc_1/chunk_1",
                    }
                ],
                "citations": [
                    {
                        "source_uri": "rag://default/doc_1/chunk_1",
                        "title": "Water guide",
                        "chunk_id": "chunk_1",
                    }
                ],
                "mapping_warnings": [],
            }
        },
    )

    VerifierAgent().verify(state)

    assert state.verification_result is not None
    assert state.verification_result["passed"] is False
    assert "claim_not_supported_by_evidence" in state.verification_result["issues"]
    assert state.draft_answer == NO_ANSWER_TEXT
    assert state.evidence_status == "low_confidence"


def test_verifier_agent_fails_closed_on_out_of_range_citation() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf water",
        intent="general_qa",
        evidence_status="success",
        draft_answer="Provide clean water [99].",
        tool_results={
            "livestock_rag_search": {
                "status": "success",
                "hits": [{"chunk_id": "chunk_1", "content": "Provide clean water."}],
                "citations": [{"source_uri": "rag://default/doc/chunk_1", "chunk_id": "chunk_1"}],
                "mapping_warnings": [],
            }
        },
    )

    VerifierAgent().verify(state)

    assert "citation_index_out_of_range" in state.verification_result["issues"]
    assert state.draft_answer == NO_ANSWER_TEXT


def test_verifier_agent_does_not_apply_livestock_claim_rules_to_ordinary_chat() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="How many grams are in 1 kg?",
        intent="out_of_scope",
        evidence_status="empty",
        draft_answer="There are 1000 g in 1 kg, which is a standard unit conversion with no investment risk.",
    )

    VerifierAgent().verify(state)

    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.errors == []
