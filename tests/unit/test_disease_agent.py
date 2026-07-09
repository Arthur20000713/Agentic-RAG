from __future__ import annotations

from typing import Any

from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMRequest


class FakePrimaryLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[PrimaryLLMRequest] = []

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        self.requests.append(request)
        return dict(self.payload)


def test_disease_agent_prepares_rag_query_without_fixed_slot_follow_up() -> None:
    state = MultiAgentState(session_id="s1", user_query="牛拉稀了怎么办？", intent="disease_consultation")

    updated = DiseaseAgent().run(state)

    assert updated is state
    assert state.active_agent == "disease_agent"
    assert state.extracted_slots == {}
    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "rag_ready"
    assert state.disease_assessment["follow_up_questions"] == []
    assert state.disease_assessment["missing_info"] == []
    assert state.rag_query is not None
    assert "牛拉稀了怎么办" in state.rag_query
    assert "livestock disease consultation" in state.rag_query
    assert "slot_extractor" not in state.tool_results
    assert "disease_slot_router" not in state.tool_results
    assert "disease_risk_evaluator" not in state.tool_results
    assert state.agent_trace[-1]["node"] == "disease_agent"
    assert state.agent_trace[-1]["status"] == "rag_ready"


def test_disease_agent_uses_normalized_query_for_dynamic_rag_query() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="用户原始输入",
        normalized_query="犊牛腹泻，精神差，不吃草",
        intent="disease_consultation",
    )

    DiseaseAgent().run(state)

    assert state.rag_query is not None
    assert "犊牛腹泻" in state.rag_query
    assert "用户原始输入" not in state.rag_query
    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "rag_ready"


def test_disease_agent_records_llm_understanding_without_turning_it_into_slots() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": False},
        primary_llm={"enabled": True, "provider": "openai_compatible", "model": "model", "base_url": "http://llm"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "case_summary": "Calf has diarrhea and reduced appetite.",
            "observed_signs": ["diarrhea", "reduced appetite"],
            "context_factors": ["young calf"],
            "information_gaps": ["feces appearance"],
            "source_spans": ["diarrhea", "reduced appetite"],
            "confidence": 0.92,
        }
    )
    state = MultiAgentState(
        session_id="s_llm_understanding",
        user_query="The calf has diarrhea and reduced appetite.",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    record = state.tool_results["disease_understanding"]
    assert record["fallback_used"] is False
    assert record["understanding"]["case_summary"] == "Calf has diarrhea and reduced appetite."
    assert record["understanding"]["observed_signs"] == ["diarrhea", "reduced appetite"]
    assert "applied_to_slots" not in record
    assert "slot_source" not in record
    assert state.extracted_slots == {}
    assert state.rag_query is not None
    assert "Calf has diarrhea" in state.rag_query
    assert "reduced appetite" in state.rag_query


def test_disease_agent_llm_understanding_failure_does_not_block_rag_query() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": False},
        primary_llm={"enabled": True, "provider": "openai_compatible", "model": "model", "base_url": "http://llm"},
    )
    llm = FakePrimaryLLM({"status": "success", "schema_name": "wrong_schema"})
    state = MultiAgentState(
        session_id="s_llm_no_block",
        user_query="羊突然不吃草，精神差",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    assert state.tool_results["disease_understanding"]["fallback_used"] is True
    assert state.rag_query is not None
    assert "羊突然不吃草" in state.rag_query
    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "rag_ready"
    assert state.errors == []
