from __future__ import annotations

from backend.app.agent.disease_reasoning import DiseaseReasoningAgent
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings


class FakeReasoningClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.called = False

    async def generate_json(self, request) -> dict:
        self.called = True
        return self.payload


def _settings(*, shadow_mode: bool = True) -> Settings:
    return Settings(
        primary_llm={"enabled": True, "provider": "mock", "model": "mock", "base_url": "mock", "api_key_env": "X"},
        disease_llm={"enabled": True, "shadow_mode": shadow_mode, "require_rag_evidence": True},
    )


def _state_with_gate(allowed: bool = True) -> MultiAgentState:
    state = MultiAgentState(session_id="s1", user_query="disease", intent="disease_consultation")
    state.extracted_slots = {"species": "cattle", "symptoms": ["diarrhea"], "duration_days": 2}
    state.tool_results["disease_evidence_gate"] = {
        "allowed": allowed,
        "status": "success" if allowed else "empty",
        "evidence_refs": [{"source_uri": "rag://livestock/doc/chunk_1", "chunk_id": "chunk_1"}] if allowed else [],
        "warnings": [],
        "error_code": None if allowed else "RAG_STATUS_NOT_SUCCESS",
    }
    state.tool_results["livestock_rag_search"] = {
        "query": "q",
        "status": "success",
        "hits": [
            {
                "chunk_id": "chunk_1",
                "document_title": "guide",
                "content": "Calf diarrhea requires hydration monitoring and veterinary support for severe cases.",
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
    }
    return state


def _valid_payload() -> dict:
    ref = {"source_uri": "rag://livestock/doc/chunk_1", "chunk_id": "chunk_1"}
    return {
        "status": "success",
        "schema_name": "disease_reasoning",
        "contributing_factors": [{"text": "Diarrhea can be related to digestive disturbance.", "evidence_refs": [ref]}],
        "uncertainties": ["Cause cannot be confirmed remotely."],
        "safe_actions": [{"text": "Monitor hydration and isolate if condition worsens.", "evidence_refs": [ref]}],
        "vet_triggers": [{"text": "Contact a vet if fever or depression appears.", "evidence_refs": [ref]}],
        "not_diagnosis_notice": "This is not a diagnosis.",
    }


def test_disease_reasoning_agent_records_shadow_result_with_item_refs() -> None:
    state = _state_with_gate()
    client = FakeReasoningClient(_valid_payload())

    DiseaseReasoningAgent(settings=_settings(), primary_llm_client=client).run(state)

    record = state.tool_results["disease_reasoning_shadow"]
    assert client.called is True
    assert record["status"] == "success"
    assert record["fallback_used"] is False
    assert record["reasoning"]["contributing_factors"][0]["evidence_refs"][0]["chunk_id"] == "chunk_1"
    assert state.agent_trace[-1]["node"] == "disease_reasoning_agent"
    assert state.agent_trace[-1]["status"] == "success"


def test_disease_reasoning_agent_does_not_call_llm_when_evidence_gate_blocks() -> None:
    state = _state_with_gate(allowed=False)
    client = FakeReasoningClient(_valid_payload())

    DiseaseReasoningAgent(settings=_settings(), primary_llm_client=client).run(state)

    record = state.tool_results["disease_reasoning_shadow"]
    assert client.called is False
    assert record["status"] == "blocked"
    assert record["fallback_reason"] == "evidence_gate_blocked:RAG_STATUS_NOT_SUCCESS"


def test_disease_reasoning_agent_rejects_items_without_valid_evidence_refs() -> None:
    payload = _valid_payload()
    payload["safe_actions"][0]["evidence_refs"] = []
    state = _state_with_gate()

    DiseaseReasoningAgent(settings=_settings(), primary_llm_client=FakeReasoningClient(payload)).run(state)

    record = state.tool_results["disease_reasoning_shadow"]
    assert record["status"] == "fallback"
    assert record["fallback_used"] is True
    assert record["fallback_reason"] == "schema_validation_failed"
    assert record["reasoning"] is None
