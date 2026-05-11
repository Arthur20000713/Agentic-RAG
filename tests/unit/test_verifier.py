from __future__ import annotations

from backend.app.agent.verifier import VerifierLite


def test_verifier_flags_professional_answer_without_citations() -> None:
    result = VerifierLite().check(
        "犊牛腹泻可能与病原感染有关，应隔离观察。",
        require_citations=True,
        citations=[],
    )

    assert result.passed is False
    assert "missing_citation" in result.issues


def test_verifier_flags_dosage() -> None:
    result = VerifierLite().check("建议使用药物 5 mg/kg。")

    assert result.passed is False
    assert "dosage" in result.issues


def test_verifier_flags_measurement_abnormal_without_evidence() -> None:
    result = VerifierLite().check(
        "胸围增长偏慢。",
        measurement_abnormal_items=["chest_girth_cm"],
        measurement_evidence=[],
    )

    assert result.passed is False
    assert "measurement_missing_evidence" in result.issues

