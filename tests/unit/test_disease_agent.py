from __future__ import annotations

from typing import Any

from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMRequest


class InvalidLocalSlotDiseaseAgent(DiseaseAgent):
    def render_local_slots(self, query: str) -> dict:
        return {"species": "cattle", "symptoms": "diarrhea"}


class FakePrimaryLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[PrimaryLLMRequest] = []

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        self.requests.append(request)
        return dict(self.payload)


def test_disease_agent_returns_follow_up_for_missing_slots() -> None:
    state = MultiAgentState(session_id="s1", user_query="牛拉稀了怎么办？", intent="disease_consultation")

    updated = DiseaseAgent().run(state)

    assert updated is state
    assert state.active_agent == "disease_agent"
    assert state.extracted_slots["species"] == "cattle"
    assert "diarrhea" in state.extracted_slots["symptoms"]
    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "follow_up"
    assert len(state.disease_assessment["follow_up_questions"]) <= 3
    assert "disease_risk_evaluator" not in state.tool_results
    assert state.rag_query is None
    assert state.draft_answer is not None
    assert "请先补充以下信息" in state.draft_answer
    assert state.agent_trace[-1]["node"] == "disease_agent"
    assert state.agent_trace[-1]["status"] == "follow_up"


def test_disease_agent_generates_assessment_and_rag_query_when_slots_are_complete() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
        intent="disease_consultation",
    )

    DiseaseAgent().run(state)

    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "success"
    assert state.disease_assessment["risk_level"] == "high"
    assert state.disease_assessment["need_vet"] is True
    assert state.tool_results["disease_risk_evaluator"]["risk_level"] == "high"
    assert state.rag_query is not None
    assert "livestock disease consultation" in state.rag_query
    assert "cattle" in state.rag_query
    assert "diarrhea" in state.rag_query
    assert "duration_days:2" in state.rag_query
    assert "temperature_c:40.2" in state.rag_query
    assert state.draft_answer is not None
    assert "初步风险等级：high" in state.draft_answer
    assert "兽医" in state.draft_answer
    assert state.agent_trace[-1]["status"] == "success"
    assert state.agent_trace[-1]["risk_level"] == "high"


def test_disease_agent_converts_risk_missing_info_to_follow_up() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
        intent="disease_consultation",
    )

    DiseaseAgent().run(state)

    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "follow_up"
    assert "species" in state.disease_assessment["missing_info"]
    assert "动物种类" in state.disease_assessment["follow_up_questions"][0]
    assert state.rag_query is None
    assert state.agent_trace[-1]["status"] == "follow_up"


def test_disease_agent_uses_normalized_query_for_slot_extraction() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="用户原始输入",
        normalized_query="犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
        intent="disease_consultation",
    )

    DiseaseAgent().run(state)

    assert state.extracted_slots["species"] == "cattle"
    assert state.disease_assessment is not None
    assert state.disease_assessment["risk_level"] == "high"
    assert state.rag_query is not None
    assert "cattle" in state.rag_query
    assert "diarrhea" in state.rag_query
    assert "duration_days:2" in state.rag_query


def test_disease_agent_uses_router_for_low_risk_slot_extraction() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )
    state = MultiAgentState(session_id="s1", user_query="犊牛腹泻了怎么办？", intent="disease_consultation")

    DiseaseAgent(settings=settings).run(state)

    assert state.extracted_slots["species"] == "cattle"
    assert "diarrhea" in state.extracted_slots["symptoms"]
    assert state.tool_results["disease_slot_router"]["route_decision"]["selected_model"] == "local_small"
    assert state.tool_results["disease_slot_router"]["fallback_used"] is False


def test_disease_agent_router_falls_back_to_rule_slots_for_high_risk_query() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )
    state = MultiAgentState(
        session_id="s1",
        user_query="多头犊牛腹泻两天，体温40.2度，精神差，不吃草，群体发病",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings).run(state)

    assert state.extracted_slots["species"] == "cattle"
    assert "diarrhea" in state.extracted_slots["symptoms"]
    assert state.tool_results["disease_slot_router"]["route_decision"]["selected_model"] == "primary"
    assert state.tool_results["disease_slot_router"]["fallback_used"] is True


def test_disease_agent_router_falls_back_when_local_slots_fail_schema() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )
    state = MultiAgentState(session_id="s1", user_query="犊牛腹泻了怎么办？", intent="disease_consultation")

    InvalidLocalSlotDiseaseAgent(settings=settings).run(state)

    assert state.extracted_slots["species"] == "cattle"
    assert "diarrhea" in state.extracted_slots["symptoms"]
    assert state.tool_results["disease_slot_router"]["route_decision"]["selected_model"] == "local_small"
    assert state.tool_results["disease_slot_router"]["fallback_used"] is True
    assert state.tool_results["disease_slot_router"]["fallback_reason"] == "local_slot_schema_invalid"


def test_disease_agent_non_shadow_llm_understanding_drives_slots_and_rag_query() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": True},
        primary_llm={"enabled": True, "provider": "openai_compatible", "model": "model", "base_url": "http://llm"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "species": "cattle",
            "age_stage": "calf",
            "symptoms_raw": ["diarrhea", "depression", "low appetite"],
            "symptoms_normalized": ["diarrhea", "depression", "low_appetite"],
            "duration_days": 2,
            "temperature_c": 40.2,
            "group_outbreak": False,
            "confidence": 0.92,
        }
    )
    state = MultiAgentState(
        session_id="s_llm_takeover",
        user_query="The animal is sick and the caretaker gave more details verbally.",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    assert state.tool_results["disease_understanding"]["applied_to_slots"] is True
    assert state.extracted_slots["species"] == "cattle"
    assert state.extracted_slots["age_stage"] == "calf"
    assert state.extracted_slots["duration_days"] == 2
    assert state.extracted_slots["temperature_c"] == 40.2
    assert state.extracted_slots["group_outbreak"] is False
    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "success"
    assert state.disease_assessment["risk_level"] == "high"
    assert state.rag_query is not None
    assert "duration_days:2.0" in state.rag_query
    assert "temperature_c:40.2" in state.rag_query
    assert "diarrhea" in state.rag_query


def test_disease_agent_non_shadow_llm_failure_respects_disabled_rule_fallback() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": False},
        primary_llm={"enabled": True, "provider": "openai_compatible", "model": "model", "base_url": "http://llm"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "species": "dragon",
            "confidence": 0.9,
        }
    )
    state = MultiAgentState(
        session_id="s_llm_no_fallback",
        user_query="犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "llm_understanding_failed"
    assert state.rag_query is None
    assert state.errors[0].error_code == "DISEASE_UNDERSTANDING_FAILED"
    assert state.tool_results["disease_understanding"]["fallback_used"] is True
