from __future__ import annotations

import json

from backend.app.evaluation.golden_runner import GoldenCase


def _load_real_cases(name: str) -> list[GoldenCase]:
    with open(f"tests/fixtures/real_golden_v4_1/{name}.json", "r", encoding="utf-8") as file:
        return [GoldenCase.model_validate(item) for item in json.load(file)]


def test_old_golden_set_schema_remains_compatible() -> None:
    with open("tests/fixtures/golden_set.json", "r", encoding="utf-8") as file:
        cases = [GoldenCase.model_validate(item) for item in json.load(file)]

    assert len(cases) == 60
    assert all(case.source_ids == [] for case in cases)
    assert all(case.language is None for case in cases)
    assert all(case.expected_answer_type is None for case in cases)


def test_real_golden_case_accepts_source_ids_language_and_answer_type() -> None:
    case = GoldenCase.model_validate(
        {
            "case_id": "REAL_ANSWERABLE_001",
            "category": "general_qa",
            "query": "断奶前犊牛腹泻观察应关注什么？",
            "source_ids": ["umn_preweaning_calf_health"],
            "language": "ZH",
            "expected_answer_type": "answerable",
            "expected": {
                "intent": "general_qa",
                "rag_call": True,
                "citation": True,
            },
        }
    )

    assert case.source_ids == ["umn_preweaning_calf_health"]
    assert case.language == "ZH"
    assert case.expected_answer_type == "answerable"


def test_real_no_answer_case_does_not_require_citation_expectation() -> None:
    case = GoldenCase.model_validate(
        {
            "case_id": "REAL_NO_ANSWER_001",
            "category": "no_answer",
            "query": "请回答一个知识库外的非畜牧问题",
            "language": "ZH",
            "expected_answer_type": "no_answer",
            "expected": {
                "intent": "general_qa",
                "rag_call": True,
                "no_answer": True,
            },
        }
    )

    assert case.expected.citation is None
    assert case.expected_answer_type == "no_answer"


def test_real_v4_1_golden_set_distribution_and_metadata() -> None:
    answerable = _load_real_cases("answerable")
    no_answer = _load_real_cases("no_answer")
    safety = _load_real_cases("safety")

    assert len(answerable) >= 12
    assert len(no_answer) >= 10
    assert len(safety) >= 8
    assert all(case.expected_answer_type == "answerable" for case in answerable)
    assert all(case.source_ids for case in answerable)
    assert all(case.expected_answer_type == "no_answer" for case in no_answer)
    assert all(case.expected.citation is None for case in no_answer)
    assert all(case.expected_answer_type == "safety_refusal" for case in safety)
