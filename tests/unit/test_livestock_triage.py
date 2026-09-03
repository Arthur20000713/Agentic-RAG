from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.app.core.config import Settings
from backend.app.model.base import BaseModelClient
from backend.app.model.livestock_triage import LivestockTriage


class RecordingClient(BaseModelClient):
    def __init__(self, payload: dict[str, Any] | BaseException) -> None:
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
        if isinstance(self.payload, BaseException):
            raise self.payload
        return dict(self.payload)


def _settings(*, shadow_mode: bool = False) -> Settings:
    return Settings(
        model_router={
            "enabled": True,
            "shadow_mode": shadow_mode,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["livestock_triage"],
        },
        local_model={"enabled": True},
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "success",
        "schema_name": "livestock_triage",
        "fallback_required": False,
        "intent_candidate": "disease_consultation",
        "confidence": 0.9,
        "slots": [
            {
                "name": "temperature_c",
                "value": 40.2,
                "source_span": "40.2°C",
                "confidence": 0.95,
            }
        ],
        "risk_candidate": "high",
        "risk_signals": ["fever"],
    }
    payload.update(overrides)
    return payload


def test_low_risk_triage_accepts_grounded_chinese_slots_in_one_call() -> None:
    client = RecordingClient(_payload())

    outcome = asyncio.run(LivestockTriage(_settings(), client=client).run("犊牛体温40.2°C，有发热"))

    assert outcome.status == "accepted"
    assert outcome.triage is not None
    assert outcome.triage.intent_candidate == "disease_consultation"
    assert outcome.triage.slots[0].source_span == "40.2°C"
    assert outcome.route_decision.selected_model == "local_small"
    assert client.calls == [
        (
            client.calls[0][0],
            "livestock_triage",
            {"user_query": "犊牛体温40.2°C，有发热"},
        )
    ]
    assert client.calls[0][0] == "犊牛体温40.2°C，有发热"
    assert "long_term_memory" not in client.calls[0][0]


@pytest.mark.parametrize("query", ["calf needs 2 mg/kg dosage", "犊牛停药期怎么处理", "多头犊牛腹泻"])
def test_high_risk_triage_is_blocked_before_calling_local_model(query: str) -> None:
    client = RecordingClient(_payload())

    outcome = asyncio.run(LivestockTriage(_settings(), client=client).run(query))

    assert outcome.status == "not_run"
    assert outcome.triage is None
    assert outcome.fallback_reason == "high_risk_requires_primary"
    assert client.calls == []


@pytest.mark.parametrize(
    ("slots", "reason"),
    [
        ([{"name": "temperature_c", "value": 40.2, "source_span": "41.5C", "confidence": 0.9}], "slot_span_not_in_query"),
        ([{"name": "temperature_c", "value": 41.5, "source_span": "40.2C", "confidence": 0.9}], "slot_value_not_in_span"),
        ([{"name": "diagnosis", "value": "pneumonia", "source_span": "calf", "confidence": 0.9}], "slot_name_not_allowed"),
        ([{"name": "group_outbreak", "value": True, "source_span": "no group outbreak", "confidence": 0.9}], "slot_value_not_in_span"),
    ],
)
def test_ungrounded_or_unsafe_slot_fails_closed(slots: list[dict[str, Any]], reason: str) -> None:
    client = RecordingClient(_payload(slots=slots))

    outcome = asyncio.run(LivestockTriage(_settings(), client=client).run("calf fever 40.2C has no group outbreak"))

    assert outcome.status == "fallback"
    assert outcome.triage is None
    assert outcome.fallback_reason == reason


def test_negated_group_outbreak_is_a_trusted_false_slot_not_an_s3_signal() -> None:
    client = RecordingClient(
        _payload(
            slots=[
                {
                    "name": "group_outbreak",
                    "value": False,
                    "source_span": "没有群体发病",
                    "confidence": 0.9,
                }
            ]
        )
    )

    outcome = asyncio.run(LivestockTriage(_settings(), client=client).run("犊牛没有群体发病，体温40.2°C"))

    assert outcome.status == "accepted"
    assert client.calls


@pytest.mark.parametrize(
    "payload",
    [
        _payload(confidence=0.69),
        _payload(status="error", fallback_required=True, error_code="LOCAL_MODEL_TIMEOUT"),
        _payload(schema_name="intent_routing"),
        _payload(intent_candidate="assistant_intro"),
        _payload(risk_candidate="low"),
        {"status": "success", "schema_name": "livestock_triage", "fallback_required": False},
    ],
)
def test_invalid_or_downgraded_local_triage_falls_back(payload: dict[str, Any]) -> None:
    client = RecordingClient(payload)

    outcome = asyncio.run(LivestockTriage(_settings(), client=client).run("calf fever 40.2°C"))

    assert outcome.status == "fallback"
    assert outcome.triage is None
    assert outcome.fallback_reason is not None
    assert client.calls


def test_shadow_mode_executes_triage_without_claiming_takeover() -> None:
    client = RecordingClient(_payload(slots=[]))

    outcome = asyncio.run(LivestockTriage(_settings(shadow_mode=True), client=client).run("calf feeding management"))

    assert outcome.status == "accepted"
    assert outcome.route_decision.route_mode == "shadow"
    assert outcome.route_decision.selected_model == "primary"
    assert client.calls


def test_local_model_failure_has_stable_fallback_reason() -> None:
    client = RecordingClient(TimeoutError("slow local model"))

    outcome = asyncio.run(LivestockTriage(_settings(), client=client).run("calf feeding management"))

    assert outcome.status == "fallback"
    assert outcome.fallback_reason == "model_error:TimeoutError"


def test_local_model_timeout_payload_preserves_its_stable_error_code() -> None:
    client = RecordingClient(_payload(status="error", fallback_required=True, error_code="LOCAL_MODEL_TIMEOUT"))

    outcome = asyncio.run(LivestockTriage(_settings(), client=client).run("calf feeding management"))

    assert outcome.status == "fallback"
    assert outcome.fallback_reason == "LOCAL_MODEL_TIMEOUT"
