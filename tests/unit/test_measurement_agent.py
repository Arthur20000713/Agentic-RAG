from __future__ import annotations

from backend.app.agent.measurement_agent import MeasurementAgent
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
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


def test_measurement_agent_render_measurement_json_preserves_rule_conclusion() -> None:
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
    state = MultiAgentState(session_id="s1", user_query="body measurement", intent="measurement_analysis")
    agent = MeasurementAgent()

    agent.run(state, measurement)
    rendered = agent.render_measurement_json(agent.measurement_service.analyze(measurement))

    assert state.measurement_report is not None
    assert rendered["animal_id"] == state.measurement_report["animal_id"]
    assert rendered["abnormal_items"] == state.measurement_report["abnormal_items"]
    assert rendered["evidence"] == state.measurement_report["evidence"]


def test_measurement_agent_adds_json_renderer_only_for_local_takeover() -> None:
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
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )
    baseline = MultiAgentState(session_id="s1", user_query="body measurement", intent="measurement_analysis")
    routed = MultiAgentState(session_id="s2", user_query="body measurement", intent="measurement_analysis")

    MeasurementAgent().run(baseline, measurement)
    MeasurementAgent(settings=settings).run(routed, measurement)

    assert routed.measurement_report == baseline.measurement_report
    assert routed.draft_answer == baseline.draft_answer
    assert "measurement_json_renderer" not in baseline.tool_results
    assert routed.tool_results["measurement_json_renderer"]["route_decision"]["selected_model"] == "local_small"
    assert routed.tool_results["measurement_json_renderer"]["report_json"]["abnormal_items"] == ["chest_girth_cm"]
