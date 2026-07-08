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
