from __future__ import annotations

from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.state import MultiAgentState


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
    assert state.rag_query == f"{state.user_query} 风险等级 high 处理原则"
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
    assert state.rag_query == "用户原始输入 风险等级 high 处理原则"
