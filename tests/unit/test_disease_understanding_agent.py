from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.disease_agent import DiseaseAgent
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


def test_disease_agent_records_llm_understanding_shadow_without_replacing_rule_slots() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": True},
        primary_llm={"enabled": True, "provider": "mock"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "species": "sheep",
            "symptoms_raw": ["不吃饭"],
            "symptoms_normalized": ["low_appetite"],
            "appetite_status": "reduced",
            "missing_critical_info": ["duration", "temperature_status", "group_outbreak"],
            "confidence": 0.83,
            "source_spans": ["羊不吃饭"],
        }
    )
    state = MultiAgentState(session_id="s1", user_query="羊不吃饭", intent="disease_consultation")

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    assert state.extracted_slots["species"] == "sheep"
    assert "low_appetite" in state.extracted_slots["symptoms"]
    assert "disease_understanding_shadow" in state.tool_results
    assert state.tool_results["disease_understanding_shadow"]["understanding"]["species"] == "sheep"
    assert state.tool_results["disease_understanding_shadow"]["fallback_used"] is False
    assert llm.requests[0].schema_name == "disease_case_understanding"
    assert "temperature_c" in (llm.requests[0].system_prompt or "")
    assert "species must be one of cattle, sheep, pig, unknown" in (llm.requests[0].system_prompt or "")
    assert state.agent_trace[-2]["node"] == "disease_understanding_agent"


def test_disease_agent_records_llm_understanding_fallback_on_invalid_json() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": True},
        primary_llm={"enabled": True, "provider": "mock"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "species": "dragon",
            "confidence": 0.9,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="羊不吃饭", intent="disease_consultation")

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding_shadow"]
    assert payload["fallback_used"] is True
    assert payload["fallback_reason"] == "schema_validation_failed"
    assert payload["rule_slots"]["species"] == "sheep"


def test_disease_agent_normalizes_deepseek_understanding_payload_before_takeover() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": False},
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "species": {"value": "bovine", "source_span": "calf"},
            "age": {"value": "3 months", "source_span": "3-month-old calf"},
            "symptoms": [
                {"value": "cough", "source_span": "coughing"},
                {"value": "fever", "source_span": "40.5 C"},
            ],
            "duration": {"value": "2 days", "days": 2, "source_span": "2 days"},
            "temperature": {"value": 40.5, "status": "fever", "source_span": "40.5 C"},
            "appetite": {"value": "reduced", "source_span": "reduced feed intake"},
            "group_outbreak": {"value": True, "source_span": "2 similar calves"},
            "confidence": 0.86,
        }
    )
    state = MultiAgentState(
        session_id="s1",
        user_query="3-month-old calf coughing with 40.5 C fever for 2 days",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding"]
    assert payload["fallback_used"] is False
    assert payload["slot_source"] == "disease_llm"
    assert payload["understanding"]["species"] == "cattle"
    assert payload["understanding"]["temperature_c"] == 40.5
    assert payload["understanding"]["duration_days"] == 2
    assert payload["understanding"]["appetite_status"] == "reduced"
    assert "calf" in payload["understanding"]["source_spans"]
    assert state.extracted_slots["species"] == "cattle"
    assert state.extracted_slots["temperature_c"] == 40.5
    assert state.extracted_slots["duration_days"] == 2
    assert state.extracted_slots["group_outbreak"] is True


def test_disease_agent_normalizes_chinese_deepseek_payload_shape() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": False},
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "species": "\u725b",
            "age": 3,
            "age_unit": "\u6708\u9f84",
            "clinical_signs": "\u54b3\u55fd\u53d1\u70e7",
            "duration": 2,
            "duration_unit": "\u5929",
            "temperature": 40.5,
            "temperature_unit": "\u5ea6",
            "feed_intake_change": "\u91c7\u98df\u4e0b\u964d",
            "similar_cases_count": 2,
            "source_spans": {
                "species": "\u5c0f\u725b",
                "clinical_signs": "\u54b3\u55fd\u53d1\u70e7",
                "temperature": "40.5\u5ea6",
            },
        }
    )
    state = MultiAgentState(
        session_id="s1",
        user_query="\u4e09\u6708\u9f84\u5c0f\u725b\u54b3\u55fd\u53d1\u70e740.5\u5ea6",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding"]
    assert payload["fallback_used"] is False
    assert payload["understanding"]["species"] == "cattle"
    assert payload["understanding"]["temperature_c"] == 40.5
    assert payload["understanding"]["temperature_status"] == "fever"
    assert payload["understanding"]["duration_days"] == 2
    assert payload["understanding"]["appetite_status"] == "reduced"
    assert payload["understanding"]["source_spans"] == ["\u5c0f\u725b", "\u54b3\u55fd\u53d1\u70e7", "40.5\u5ea6"]
    assert state.extracted_slots["species"] == "cattle"
    assert state.extracted_slots["group_outbreak"] is True


def test_disease_agent_unwraps_schema_named_understanding_payload() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": False},
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "disease_case_understanding",
            "disease_case_understanding": {
                "species": "\u725b",
                "clinical_signs": "\u54b3\u55fd\u53d1\u70e7",
                "duration": "2\u5929",
                "temperature": "40.5\u2103",
                "feed_intake_change": "\u91c7\u98df\u4e0b\u964d",
                "herd_similar_count": 2,
            },
        }
    )
    state = MultiAgentState(
        session_id="s1",
        user_query="\u5c0f\u725b\u54b3\u55fd\u53d1\u70e740.5\u5ea6",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding"]
    assert payload["fallback_used"] is False
    assert payload["understanding"]["species"] == "cattle"
    assert payload["understanding"]["temperature_c"] == 40.5
    assert state.extracted_slots["group_outbreak"] is True


def test_disease_agent_normalizes_alternate_deepseek_field_names() -> None:
    settings = Settings(
        disease_llm={"enabled": True, "shadow_mode": False, "allow_rule_fallback": False},
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "incomplete",
            "schema_name": "disease_case_understanding",
            "species": "\u5c0f\u725b",
            "species_span": "\u5c0f\u725b",
            "symptoms": ["\u54b3\u55fd", "\u53d1\u70e7", "\u91c7\u98df\u4e0b\u964d"],
            "symptoms_span": "\u54b3\u55fd\u53d1\u70e7",
            "duration": 2,
            "duration_span": "\u6301\u7eed2\u5929",
            "fever_temperature": 40.5,
            "fever_temperature_span": "40.5\u5ea6",
            "similar_cases": 2,
            "similar_cases_span": "\u8fd8\u67092\u5934\u7c7b\u4f3c",
            "confidence": "high",
            "source_spans": "\u5c0f\u725b\u54b3\u55fd\u53d1\u70e740.5\u5ea6",
        }
    )
    state = MultiAgentState(
        session_id="s1",
        user_query="\u5c0f\u725b\u54b3\u55fd\u53d1\u70e740.5\u5ea6",
        intent="disease_consultation",
    )

    DiseaseAgent(settings=settings, primary_llm_client=llm).run(state)

    payload = state.tool_results["disease_understanding"]
    assert payload["fallback_used"] is False
    assert payload["understanding"]["species"] == "cattle"
    assert payload["understanding"]["temperature_c"] == 40.5
    assert payload["understanding"]["appetite_status"] == "reduced"
    assert "\u5c0f\u725b\u54b3\u55fd\u53d1\u70e740.5\u5ea6" in payload["understanding"]["source_spans"]
    assert state.extracted_slots["group_outbreak"] is True
