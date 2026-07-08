from __future__ import annotations

from backend.app.agent.extractor import SlotExtractor, build_follow_up_questions


def test_slot_extractor_extracts_disease_slots() -> None:
    slots = SlotExtractor().extract("犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病")

    assert slots.species == "cattle"
    assert slots.age_stage == "calf"
    assert "diarrhea" in slots.symptoms
    assert "depression" in slots.symptoms
    assert "low_appetite" in slots.symptoms
    assert slots.temperature_c == 40.2
    assert slots.duration_days == 2
    assert slots.group_outbreak is False


def test_follow_up_questions_are_limited_to_three() -> None:
    slots = SlotExtractor().extract("牛拉稀了怎么办？")

    questions = build_follow_up_questions(slots)

    assert len(questions) <= 3
    joined = " ".join(questions)
    assert "持续" in joined
    assert "体温" in joined
    assert "群体" in joined


def test_slot_extractor_understands_plain_follow_up_answers() -> None:
    slots = SlotExtractor().extract("1天了，正常体温，就一只这样")

    assert slots.duration_days == 1
    assert slots.temperature_c == 39.0
    assert slots.group_outbreak is False
