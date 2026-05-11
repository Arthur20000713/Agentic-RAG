from __future__ import annotations

import asyncio

from backend.app.agent.workflow import run_measurement_analysis
from backend.app.schemas.measurement import MeasurementInput


def test_measurement_workflow_without_history() -> None:
    measurement = MeasurementInput(
        animal_id="yak_001",
        current={"body_height_cm": 114.2, "weight_kg": 246.5},
        confidence=0.82,
    )

    state = asyncio.run(run_measurement_analysis(measurement, session_id="s_measure_none"))

    assert state.intent == "measurement_analysis"
    assert state.final_answer is not None
    assert "无历史记录" in state.final_answer
    assert state.tool_results["body_measurement_analyzer"]["abnormal_items"] == []


def test_measurement_workflow_with_history_and_evidence() -> None:
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

    state = asyncio.run(run_measurement_analysis(measurement, session_id="s_measure_history"))

    assert state.final_answer is not None
    assert "增长 1.4 cm" in state.final_answer
    assert "chest_girth_cm" in state.tool_results["body_measurement_analyzer"]["abnormal_items"]


def test_measurement_workflow_marks_demo_history() -> None:
    measurement = MeasurementInput(
        animal_id="yak_demo",
        current={"chest_girth_cm": 158.4},
        history=[{"measure_date": "2026-04-01", "chest_girth_cm": 157.0}],
        confidence=0.82,
        use_demo_history=True,
    )

    state = asyncio.run(run_measurement_analysis(measurement, session_id="s_measure_demo"))

    assert state.final_answer is not None
    assert "演示数据" in state.final_answer
    assert state.tool_results["body_measurement_analyzer"]["used_demo_history"] is True

