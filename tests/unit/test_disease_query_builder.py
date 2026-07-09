from __future__ import annotations

from backend.app.agent.disease_query_builder import DiseaseQueryBuilder
from backend.app.agent.state import MultiAgentState


def test_disease_query_builder_uses_user_query_when_no_understanding_exists() -> None:
    state = MultiAgentState(session_id="s1", user_query="羊不吃饭怎么办？", intent="disease_consultation")

    result = DiseaseQueryBuilder().build(state)

    assert "livestock disease consultation" in result.query
    assert "羊不吃饭怎么办" in result.query
    assert result.facts == {}
    assert result.warnings == ["disease_query_used_raw_user_message_only"]
    assert "temperature_c:" not in result.query
    assert "duration_days:" not in result.query


def test_disease_query_builder_uses_dynamic_understanding_terms() -> None:
    state = MultiAgentState(session_id="s2", user_query="raw", intent="disease_consultation")
    state.tool_results["disease_understanding"] = {
        "understanding": {
            "case_summary": "Calf has diarrhea after feed change.",
            "species": "cattle",
            "observed_signs": ["diarrhea", "depression"],
            "context_factors": ["feed change", "young calf"],
            "explicit_user_facts": {"caretaker_note": "condition worsened overnight"},
            "information_gaps": ["feces color"],
        }
    }

    result = DiseaseQueryBuilder().build(state)

    assert "Calf has diarrhea after feed change." in result.query
    assert "feed change" in result.query
    assert "condition worsened overnight" in result.query
    assert "feces color" in result.query
    assert result.facts["observed_signs"] == ["diarrhea", "depression"]
    assert result.warnings == []


def test_disease_query_builder_falls_back_to_session_understanding() -> None:
    state = MultiAgentState(
        session_id="s3",
        user_query="今天更严重了",
        intent="disease_consultation",
        session_context={
            "last_understanding": {
                "case_summary": "Sheep has reduced appetite.",
                "observed_signs": ["reduced appetite"],
                "context_factors": ["normal temperature"],
            }
        },
    )

    result = DiseaseQueryBuilder().build(state)

    assert "今天更严重了" in result.query
    assert "Sheep has reduced appetite." in result.query
    assert "normal temperature" in result.query
