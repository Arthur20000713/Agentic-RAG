from __future__ import annotations

from backend.app.rules.disease_risk import DiseaseRiskEvaluator


def test_disease_risk_returns_missing_info_for_required_slots() -> None:
    result = DiseaseRiskEvaluator().evaluate(
        species="cattle",
        symptoms=["diarrhea"],
    )

    assert result.status == "missing_info"
    assert "temperature_c" in result.missing_info
    assert "duration_days" in result.missing_info
    assert "group_outbreak" in result.missing_info


def test_emergency_overrides_high_risk() -> None:
    result = DiseaseRiskEvaluator().evaluate(
        species="cattle",
        symptoms=["diarrhea", "depression", "sudden_death"],
        temperature_c=40.5,
        duration_days=2,
        group_outbreak=True,
    )

    assert result.risk_level == "emergency"
    assert result.need_vet is True
    assert result.need_isolation is True
    assert "群体" in result.reason


def test_high_risk_for_fever_and_digestive_symptoms() -> None:
    result = DiseaseRiskEvaluator().evaluate(
        species="cattle",
        symptoms=["diarrhea", "low_appetite", "depression"],
        temperature_c=40.2,
        duration_days=2,
        group_outbreak=False,
    )

    assert result.status == "success"
    assert result.risk_level == "high"
    assert result.need_vet is True

