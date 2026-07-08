from __future__ import annotations

from backend.app.agent.disease_query_builder import DiseaseQueryBuilder
from backend.app.agent.state import MultiAgentState


def test_disease_query_builder_uses_facts_and_ignores_llm_diagnosis_guesses() -> None:
    state = MultiAgentState(session_id="s1", user_query="sheep stopped eating", intent="disease_consultation")
    state.extracted_slots = {
        "species": "sheep",
        "symptoms": ["low_appetite"],
        "duration_days": 1,
        "temperature_c": 39.0,
        "group_outbreak": False,
    }
    state.tool_results["disease_understanding"] = {
        "understanding": {
            "species": "sheep",
            "symptoms_normalized": ["low_appetite"],
            "duration_text": "1 day",
            "temperature_status": "normal",
            "group_outbreak": False,
            "suspected_disease": "enterotoxemia",
            "likely_diagnosis": "enterotoxemia",
        }
    }

    result = DiseaseQueryBuilder().build(state)

    assert result.query
    assert "sheep" in result.query
    assert "low_appetite" in result.query
    assert "duration_days:1" in result.query
    assert "temperature_c:39.0" in result.query
    assert "group_outbreak:false" in result.query
    assert "enterotoxemia" not in result.query
    assert "diagnosis" not in result.query.lower()


def test_disease_query_builder_falls_back_to_session_confirmed_fields() -> None:
    state = MultiAgentState(
        session_id="s2",
        user_query="still weak",
        intent="disease_consultation",
        session_context={
            "confirmed_case_fields": {
                "species": "cattle",
                "symptoms": ["diarrhea", "depression"],
                "duration_days": 2,
            }
        },
    )

    result = DiseaseQueryBuilder().build(state)

    assert "cattle" in result.query
    assert "diarrhea" in result.query
    assert "depression" in result.query
    assert "duration_days:2" in result.query
