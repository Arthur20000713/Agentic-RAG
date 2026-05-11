from __future__ import annotations

from collections import Counter
import json

from backend.app.evaluation.golden_runner import GoldenCase


def _cases() -> list[GoldenCase]:
    with open("tests/fixtures/golden_set.json", "r", encoding="utf-8") as file:
        return [GoldenCase.model_validate(item) for item in json.load(file)]


def test_golden_set_schema_validates_all_cases() -> None:
    cases = _cases()

    assert len(cases) == 60
    assert all(case.case_id for case in cases)
    assert len({case.case_id for case in cases}) == 60


def test_golden_set_knowledge_cases_distribution() -> None:
    counts = Counter(case.category for case in _cases())

    assert counts["general_qa"] == 10
    assert counts["feeding_management"] == 10


def test_golden_set_disease_cases_distribution() -> None:
    counts = Counter(case.category for case in _cases())

    assert counts["disease_consultation"] == 15
    assert counts["high_risk_refusal"] == 10


def test_golden_set_measurement_and_no_answer_distribution() -> None:
    counts = Counter(case.category for case in _cases())

    assert counts["measurement_analysis"] == 10
    assert counts["no_answer"] == 5
