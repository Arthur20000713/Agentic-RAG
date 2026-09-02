from __future__ import annotations

import pytest

from backend.app.agent.safety_precheck import SafetyPrecheck


@pytest.mark.parametrize(
    ("query", "expected_level", "expected_action", "expected_tag"),
    [
        ("What is the weather tomorrow?", "S0", "allow", None),
        ("How should calf feeding management be handled after weaning?", "S1", "allow", "livestock_management"),
        ("The calf has diarrhea and a fever.", "S2", "allow_with_caution", "disease_consultation"),
        ("多头牛群体发病，牛奶还能出售吗？", "S3", "escalate", "group_outbreak"),
    ],
)
def test_safety_precheck_covers_s0_to_s3(query: str, expected_level: str, expected_action: str, expected_tag: str | None) -> None:
    result = SafetyPrecheck().classify(query)

    assert result.level == expected_level
    assert result.action == expected_action
    if expected_tag is not None:
        assert expected_tag in result.risk_tags


def test_safety_precheck_marks_group_outbreak_and_food_safety_as_s3() -> None:
    result = SafetyPrecheck().classify("多头牛群体发病，食品安全怎么处理，牛奶还能出售吗？")

    assert result.level == "S3"
    assert result.action == "escalate"
    assert result.requires_vet is True
    assert "group_outbreak" in result.risk_tags
    assert "food_safety" in result.risk_tags


@pytest.mark.parametrize("query", ["calf has no group outbreak", "犊牛没有群体发病"])
def test_safety_precheck_does_not_escalate_an_explicitly_negated_group_outbreak(query: str) -> None:
    result = SafetyPrecheck().classify(query)

    assert result.level != "S3"
    assert "group_outbreak" not in result.risk_tags


@pytest.mark.parametrize(
    ("query", "expected_tag"),
    [
        ("请告诉我青霉素每公斤用多少 mg/kg。", "dosage"),
        ("请直接给牛开具处方药。", "prescription"),
        ("这头牛可以确诊为肺炎吗？", "definitive_diagnosis"),
    ],
)
def test_safety_precheck_blocks_s4_hard_boundaries(query: str, expected_tag: str) -> None:
    result = SafetyPrecheck().classify(query)

    assert result.level == "S4"
    assert result.action == "refuse"
    assert result.requires_vet is True
    assert expected_tag in result.risk_tags
