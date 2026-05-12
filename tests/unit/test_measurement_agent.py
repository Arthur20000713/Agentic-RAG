from __future__ import annotations

from backend.app.agent.measurement_agent import MeasurementAgent
from backend.app.agent.state import MultiAgentState
from backend.app.schemas.measurement import MeasurementInput


def test_measurement_agent_generates_report_without_rag_call() -> None:
    measurement = MeasurementInput(
        animal_id="yak_032",
        current={"chest_girth_cm": 158.4, "weight_kg": 246.5},
        history=[
            {
                "measure_date": "2026-04-01",
                "chest_girth_cm": 157.0,
                "weight_kg": 242.0,
            }
        ],
        confidence=0.82,
    )
    state = MultiAgentState(session_id="s1", user_query="analyze yak measurement", intent="measurement_analysis")

    updated = MeasurementAgent().run(state, measurement)

    assert updated is state
    assert state.active_agent == "measurement_agent"
    assert state.measurement_report is not None
    assert state.measurement_report["animal_id"] == "yak_032"
    assert "chest_girth_cm" in state.measurement_report["abnormal_items"]
    assert state.tool_results["body_measurement_analyzer"] == state.measurement_report
    assert state.draft_answer is not None
    assert "增长 1.4 cm" in state.draft_answer
    assert "livestock_rag_search" not in state.tool_results
    assert state.rag_query is None
    assert state.agent_trace[-1]["node"] == "measurement_agent"
    assert state.agent_trace[-1]["status"] == "success"
    assert state.agent_trace[-1]["abnormal_count"] == 1


def test_measurement_agent_preserves_no_history_boundary() -> None:
    measurement = MeasurementInput(
        animal_id="yak_001",
        current={"body_height_cm": 114.2, "weight_kg": 246.5},
        confidence=0.82,
    )
    state = MultiAgentState(session_id="s1", user_query="body measurement", intent="measurement_analysis")

    MeasurementAgent().run(state, measurement)

    assert state.measurement_report is not None
    assert state.measurement_report["abnormal_items"] == []
    assert "无历史记录" in state.measurement_report["summary"]
    assert state.agent_trace[-1]["abnormal_count"] == 0


def test_measurement_agent_marks_demo_history() -> None:
    measurement = MeasurementInput(
        animal_id="yak_demo",
        current={"chest_girth_cm": 158.4},
        confidence=0.82,
        use_demo_history=True,
    )
    state = MultiAgentState(session_id="s1", user_query="body measurement", intent="measurement_analysis")

    MeasurementAgent().run(state, measurement)

    assert state.measurement_report is not None
    assert state.measurement_report["used_demo_history"] is True
    assert state.draft_answer is not None
    assert "演示数据" in state.draft_answer
    assert state.agent_trace[-1]["used_demo_history"] is True
