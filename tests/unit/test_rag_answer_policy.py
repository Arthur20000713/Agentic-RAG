from __future__ import annotations

from backend.app.agent.rag_answer_policy import (
    NO_ANSWER_POLICY_WARNING,
    SAFETY_REFUSAL_POLICY_WARNING,
    build_insufficient_evidence_answer,
    classify_rag_answer_policy,
)


def test_policy_marks_out_of_corpus_species_as_no_answer() -> None:
    decision = classify_rag_answer_policy("What does this cattle corpus say about pet cat vaccination schedules?")

    assert decision.force_no_answer is True
    assert decision.warning == NO_ANSWER_POLICY_WARNING
    assert decision.should_use_retrieved_contexts is False


def test_policy_marks_empty_knowledge_base_eval_sentinel_as_no_answer() -> None:
    decision = classify_rag_answer_policy("empty knowledge-base question 1")

    assert decision.force_no_answer is True
    assert decision.warning == NO_ANSWER_POLICY_WARNING
    assert decision.should_use_retrieved_contexts is False


def test_policy_marks_dosage_request_as_safety_refusal() -> None:
    decision = classify_rag_answer_policy("犊牛腹泻两天，请直接告诉我庆大霉素每公斤打多少毫克。")

    assert decision.force_safety_refusal is True
    assert decision.warning == SAFETY_REFUSAL_POLICY_WARNING
    assert decision.should_require_citations is False


def test_policy_marks_sick_calf_mixing_as_safety_refusal() -> None:
    decision = classify_rag_answer_policy("Can I mix sick calves with healthy calves to save labor if symptoms are mild?")

    assert decision.force_safety_refusal is True
    assert decision.warning == SAFETY_REFUSAL_POLICY_WARNING


def test_policy_allows_regular_calf_management_question() -> None:
    decision = classify_rag_answer_policy("断奶前犊牛腹泻观察应记录哪些变化？")

    assert decision.force_no_answer is False
    assert decision.force_safety_refusal is False
    assert decision.should_use_retrieved_contexts is True


def test_policy_allows_supported_livestock_species_to_reach_real_rag() -> None:
    for query in (
        "How should poultry be managed in summer?",
        "What should swine farrowing management emphasize?",
        "How should goats be housed in winter?",
    ):
        decision = classify_rag_answer_policy(query)

        assert decision.force_no_answer is False
        assert decision.should_use_retrieved_contexts is True


def test_insufficient_answer_bounds_and_sanitizes_follow_up_questions() -> None:
    answer = build_insufficient_evidence_answer(
        "How should the calf be managed?",
        missing_aspects=["age [1]", "body weight", "age [1]", "current ration", "housing"],
        has_conflicts=False,
    )

    assert answer.count("\n- ") == 3
    assert "[1]" not in answer
    assert "age?" in answer
    assert "body weight?" in answer
    assert "current ration?" in answer
    assert "housing" not in answer


def test_insufficient_answer_reports_conflict_without_citation_marker() -> None:
    answer = build_insufficient_evidence_answer(
        "犊牛应该怎么喂？",
        missing_aspects=[],
        has_conflicts=True,
    )

    assert "证据存在尚未解决的冲突" in answer
    assert "人工复核" in answer
    assert "[1]" not in answer
