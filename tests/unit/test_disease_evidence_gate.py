from __future__ import annotations

from backend.app.agent.disease_evidence_gate import DiseaseEvidenceGate
from backend.app.agent.state import MultiAgentState


def _state_with_rag_result(rag_result: dict) -> MultiAgentState:
    state = MultiAgentState(session_id="s1", user_query="disease question", intent="disease_consultation")
    state.tool_results["livestock_rag_search"] = rag_result
    state.evidence_status = rag_result.get("status")
    return state


def test_disease_evidence_gate_allows_success_with_item_refs() -> None:
    state = _state_with_rag_result(
        {
            "query": "q",
            "status": "success",
            "hits": [
                {
                    "chunk_id": "chunk_1",
                    "document_title": "guide",
                    "content": "context",
                    "source_uri": "rag://livestock/doc/chunk_1",
                    "score": 0.9,
                }
            ],
            "citations": [
                {
                    "title": "guide",
                    "source_uri": "rag://livestock/doc/chunk_1",
                    "chunk_id": "chunk_1",
                }
            ],
            "mapping_warnings": [],
        }
    )

    result = DiseaseEvidenceGate().evaluate(state)

    assert result.allowed is True
    assert result.error_code is None
    assert result.evidence_refs == [{"source_uri": "rag://livestock/doc/chunk_1", "chunk_id": "chunk_1"}]


def test_disease_evidence_gate_rejects_empty_low_confidence_or_error() -> None:
    for status in ("empty", "low_confidence", "error"):
        result = DiseaseEvidenceGate().evaluate(_state_with_rag_result({"query": "q", "status": status}))

        assert result.allowed is False
        assert result.error_code == "RAG_STATUS_NOT_SUCCESS"


def test_disease_evidence_gate_rejects_missing_refs_and_partial_mapping() -> None:
    missing_refs = DiseaseEvidenceGate().evaluate(
        _state_with_rag_result(
            {
                "query": "q",
                "status": "success",
                "hits": [{"chunk_id": "chunk_1", "document_title": "guide", "content": "context", "score": 0.7}],
                "citations": [{"title": "guide", "chunk_id": "chunk_1"}],
                "mapping_warnings": [],
            }
        )
    )
    partial_mapping = DiseaseEvidenceGate().evaluate(
        _state_with_rag_result(
            {
                "query": "q",
                "status": "success",
                "hits": [
                    {
                        "chunk_id": "chunk_1",
                        "document_title": "guide",
                        "content": "context",
                        "source_uri": "rag://livestock/doc/chunk_1",
                        "score": 0.7,
                    }
                ],
                "citations": [
                    {
                        "title": "guide",
                        "source_uri": "rag://livestock/doc/chunk_1",
                        "chunk_id": "chunk_1",
                    }
                ],
                "mapping_warnings": ["RAG_MAPPING_PARTIAL_SOURCE_URI"],
            }
        )
    )

    assert missing_refs.allowed is False
    assert missing_refs.error_code == "RAG_VALID_EVIDENCE_MISSING"
    assert partial_mapping.allowed is False
    assert partial_mapping.error_code == "RAG_SOURCE_MAPPING_WARNING"
