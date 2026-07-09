from __future__ import annotations

from typing import Any

from backend.app.agent.disease_understanding import DiseaseUnderstandingAgent
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMRequest


class FakePrimaryLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[PrimaryLLMRequest] = []

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        self.requests.append(request)
        return dict(self.payload)


def _settings(*, shadow_mode: bool = False) -> Settings:
    return Settings(
        disease_llm={"enabled": True, "shadow_mode": shadow_mode},
        primary_llm={"enabled": True, "provider": "openai_compatible", "model": "model", "base_url": "http://llm"},
    )


def test_disease_understanding_records_dynamic_case_context() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "case_summary": "Sheep has reduced appetite and normal temperature.",
            "species": "sheep",
            "observed_signs": ["reduced appetite"],
            "context_factors": ["normal temperature"],
            "explicit_user_facts": {"duration": "one day"},
            "information_gaps": ["feces appearance"],
            "source_spans": ["reduced appetite", "normal temperature"],
            "confidence": "high",
        }
    )
    state = MultiAgentState(session_id="s1", user_query="羊不吃饭，一天了，体温正常", intent="disease_consultation")

    DiseaseUnderstandingAgent(settings=_settings(), primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding"]
    assert payload["fallback_used"] is False
    understanding = payload["understanding"]
    assert understanding["case_summary"] == "Sheep has reduced appetite and normal temperature."
    assert understanding["species"] == "sheep"
    assert understanding["observed_signs"] == ["reduced appetite"]
    assert understanding["context_factors"] == ["normal temperature"]
    assert understanding["explicit_user_facts"] == {"duration": "one day", "species": "sheep"}
    assert understanding["information_gaps"] == ["feces appearance"]
    assert understanding["confidence"] == 0.85
    assert "do not force a fixed slot list" in (llm.requests[0].system_prompt or "").lower()


def test_disease_understanding_maps_legacy_llm_fields_without_slot_application() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "species": "cattle",
            "symptoms_normalized": ["diarrhea", "depression"],
            "temperature_status": "fever",
            "group_outbreak": {"value": True, "source_span": "2 similar calves"},
            "confidence": 0.7,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="two calves have diarrhea", intent="disease_consultation")

    DiseaseUnderstandingAgent(settings=_settings(), primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding"]
    understanding = payload["understanding"]
    assert payload["fallback_used"] is False
    assert understanding["observed_signs"] == ["diarrhea", "depression"]
    assert understanding["context_factors"] == ["temperature_status: fever", "group_outbreak: True"]
    assert understanding["explicit_user_facts"]["species"] == "cattle"
    assert understanding["explicit_user_facts"]["temperature_status"] == "fever"
    assert understanding["explicit_user_facts"]["group_outbreak"] is True
    assert understanding["source_spans"] == ["2 similar calves"]
    assert "applied_to_slots" not in payload
    assert state.extracted_slots == {}


def test_disease_understanding_shadow_mode_uses_shadow_key() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "case_summary": "Pig cough case.",
            "observed_signs": ["cough"],
        }
    )
    state = MultiAgentState(session_id="s1", user_query="猪咳嗽", intent="disease_consultation")

    DiseaseUnderstandingAgent(settings=_settings(shadow_mode=True), primary_llm_client=llm).run(state)

    assert "disease_understanding_shadow" in state.tool_results
    assert "disease_understanding" not in state.tool_results
    assert state.tool_results["disease_understanding_shadow"]["understanding"]["observed_signs"] == ["cough"]


def test_disease_understanding_invalid_schema_falls_back_without_errors() -> None:
    llm = FakePrimaryLLM({"status": "success", "schema_name": "wrong"})
    state = MultiAgentState(session_id="s1", user_query="羊不吃饭", intent="disease_consultation")

    DiseaseUnderstandingAgent(settings=_settings(), primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding"]
    assert payload["fallback_used"] is True
    assert payload["fallback_reason"] == "schema_validation_failed"
    assert payload["understanding"] is None
