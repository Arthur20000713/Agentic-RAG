from __future__ import annotations

from backend.app.schemas.measurement import MeasurementInput
from backend.app.services.measurement_service import BodyMeasurementAnalyzer


def test_measurement_without_history_does_not_report_trend() -> None:
    measurement = MeasurementInput(
        animal_id="yak_001",
        current={"body_height_cm": 114.2, "weight_kg": 246.5},
        confidence=0.82,
    )

    result = BodyMeasurementAnalyzer().analyze(measurement)

    assert result.used_demo_history is False
    assert result.abnormal_items == []
    assert "趋势" not in "".join(result.evidence)
    assert "无历史记录" in result.summary


def test_measurement_abnormal_item_has_numeric_evidence() -> None:
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

    result = BodyMeasurementAnalyzer().analyze(measurement)

    assert "chest_girth_cm" in result.abnormal_items
    assert any("157.0 cm" in item and "158.4 cm" in item for item in result.evidence)
    assert "增长 1.4 cm" in result.report


def test_measurement_low_confidence_recommends_remeasure() -> None:
    measurement = MeasurementInput(
        animal_id="yak_002",
        current={"body_height_cm": 110.0},
        confidence=0.52,
    )

    result = BodyMeasurementAnalyzer().analyze(measurement)

    assert "复测" in result.recommendation

