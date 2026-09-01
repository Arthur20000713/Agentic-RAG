from __future__ import annotations

import asyncio
from typing import Any

from backend.app.core.config import Settings
from backend.app.model.intent_router import route_intent_with_model


class FakeIntentClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((prompt, schema_name, context))
        return dict(self.payload)


def _settings() -> Settings:
    return Settings(
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["intent_routing"],
        },
        local_model={"enabled": True},
    )


def test_route_intent_with_model_uses_local_structured_result() -> None:
    client = FakeIntentClient(
        {
            "status": "success",
            "schema_name": "intent_routing",
            "intent": "disease_consultation",
            "confidence": 0.91,
            "should_use_rag": True,
            "should_use_tools": ["disease_agent"],
            "reason": "symptoms and animal species",
            "fallback_required": False,
        }
    )

    result = asyncio.run(route_intent_with_model("calf diarrhea and fever", settings=_settings(), client=client))

    assert result.intent == "disease_consultation"
    assert result.confidence == 0.91
    assert result.should_use_rag is True
    assert result.should_use_tools == ["disease_agent"]
    assert result.fallback_used is False
    assert result.selected_model == "local_small"
    assert client.calls[0][1] == "intent_routing"
    assert client.calls[0][2]["allowed_intents"] == [
        "assistant_intro",
        "general_qa",
        "disease_consultation",
        "measurement_analysis",
        "out_of_scope",
    ]


def test_route_intent_with_model_excludes_long_term_memory_from_model_context() -> None:
    poison = "MEMORY_INSTRUCTION_OVERRIDE"
    client = FakeIntentClient(
        {
            "status": "success",
            "schema_name": "intent_routing",
            "intent": "general_qa",
            "confidence": 0.91,
            "should_use_rag": True,
            "reason": "livestock management",
        }
    )

    asyncio.run(
        route_intent_with_model(
            "How should calf feeding be managed?",
            settings=_settings(),
            client=client,
            session_context={
                "last_intent": "general_qa",
                "long_term_memory": [{"content": poison}],
            },
        )
    )

    model_context = client.calls[0][2]
    assert model_context is not None
    assert model_context["session_context"] == {"last_intent": "general_qa"}
    assert poison not in str(model_context)


def test_route_intent_with_model_falls_back_to_rules_on_schema_error() -> None:
    client = FakeIntentClient({"status": "success", "schema_name": "intent_routing", "intent": "unknown"})

    result = asyncio.run(route_intent_with_model("Calf diarrhea and fever", settings=_settings(), client=client))

    assert result.intent == "disease_consultation"
    assert result.fallback_used is True
    assert result.fallback_reason == "schema_validation_failed"
    assert result.selected_model == "local_small"


def test_route_intent_with_model_keeps_general_qa_rag_enabled_even_if_model_says_direct() -> None:
    client = FakeIntentClient(
        {
            "status": "success",
            "schema_name": "intent_routing",
            "intent": "general_qa",
            "confidence": 0.88,
            "should_use_rag": False,
            "should_use_tools": [],
            "reason": "livestock management",
            "fallback_required": False,
        }
    )

    result = asyncio.run(route_intent_with_model("How should calf feeding be managed?", settings=_settings(), client=client))

    assert result.intent == "general_qa"
    assert result.should_use_rag is True
    assert result.fallback_used is False


def test_route_intent_with_model_guardrails_greeting_away_from_rag_when_model_is_inconsistent() -> None:
    client = FakeIntentClient(
        {
            "status": "success",
            "schema_name": "intent_routing",
            "intent": "general_qa",
            "confidence": 1.0,
            "should_use_rag": True,
            "should_use_tools": [],
            "reason": "greeting",
            "fallback_required": False,
        }
    )

    result = asyncio.run(route_intent_with_model("hello", settings=_settings(), client=client))

    assert result.intent == "assistant_intro"
    assert result.should_use_rag is False
    assert result.fallback_used is True
    assert result.fallback_reason == "direct_intent_guardrail"


def test_route_intent_with_model_guardrails_ordinary_chat_away_from_rag() -> None:
    client = FakeIntentClient(
        {
            "status": "success",
            "schema_name": "intent_routing",
            "intent": "general_qa",
            "confidence": 1.0,
            "should_use_rag": True,
            "should_use_tools": [],
            "reason": "incorrect livestock classification",
            "fallback_required": False,
        }
    )

    result = asyncio.run(route_intent_with_model("Tell me a short joke.", settings=_settings(), client=client))

    assert result.intent == "out_of_scope"
    assert result.should_use_rag is False
    assert result.fallback_used is True
    assert result.fallback_reason == "direct_intent_guardrail"
