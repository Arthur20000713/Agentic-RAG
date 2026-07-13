from __future__ import annotations

from backend.app.agent.safety_agent import SafetyAgent
from backend.app.agent.state import MultiAgentState


def test_safety_agent_passes_safe_answer() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="disease_consultation",
        draft_answer="建议继续观察体温、采食状态和粪便变化，必要时联系兽医。",
    )

    updated = SafetyAgent().check(state)

    assert updated is state
    assert state.active_agent == "safety_agent"
    assert state.final_answer == state.draft_answer
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.safety_result["violations"] == []
    assert state.errors == []
    assert state.agent_trace[-1]["node"] == "safety_agent"
    assert state.agent_trace[-1]["status"] == "success"


def test_safety_agent_blocks_specific_dosage() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="disease_consultation",
        draft_answer="建议使用药物 5 mg/kg。",
    )

    SafetyAgent().check(state)

    assert state.safety_result is not None
    assert state.safety_result["passed"] is False
    assert "dosage" in state.safety_result["violations"]
    assert state.final_answer is not None
    assert "5 mg/kg" not in state.final_answer
    assert "不能提供具体药物剂量" in state.final_answer
    assert state.safety_result["hard_blocked"] is True
    assert state.safety_result["hard_violations"] == ["dosage"]
    assert state.errors[-1].tool_name == "safety_agent"
    assert state.errors[-1].error_code == "dosage"
    assert state.agent_trace[-1]["status"] == "blocked"


def test_safety_agent_blocks_definitive_diagnosis() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="disease_consultation",
        draft_answer="可以确定诊断为牛瘟。",
    )

    SafetyAgent().check(state)

    assert state.safety_result is not None
    assert "definitive_diagnosis" in state.safety_result["violations"]
    assert state.safety_result["hard_blocked"] is True
    assert state.final_answer is not None
    assert "确定诊断" not in state.final_answer
    assert any(error.error_code == "definitive_diagnosis" for error in state.errors)


def test_safety_agent_blocks_prescription_as_hard_boundary() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="disease_consultation",
        draft_answer="请直接给这头牛开处方，使用抗生素处方药。",
    )

    SafetyAgent().check(state)

    assert state.safety_result is not None
    assert "prescription" in state.safety_result["violations"]
    assert state.safety_result["hard_blocked"] is True
    assert state.final_answer is not None
    assert "处方药" not in state.final_answer
    assert any(error.error_code == "prescription" for error in state.errors)


def test_safety_agent_blocks_fabricated_tool_result_claim() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="calf diarrhea",
        intent="general_qa",
        draft_answer="虽然工具调用失败，但检索结果显示应立即用药。",
    )

    SafetyAgent().check(state)

    assert state.safety_result is not None
    assert "fabricated_tool_result" in state.safety_result["violations"]
    assert state.final_answer is not None
    assert "检索结果显示" not in state.final_answer
    assert state.tool_results["safety_agent"] == state.safety_result


def test_safety_agent_does_not_treat_ordinary_unit_conversion_as_drug_dosage() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="How many grams are in 1 kg?",
        intent="out_of_scope",
        draft_answer="1 kg equals 1000 g.",
    )

    SafetyAgent().check(state)

    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.final_answer == "1 kg equals 1000 g."
