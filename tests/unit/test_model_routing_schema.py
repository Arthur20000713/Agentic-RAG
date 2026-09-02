from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.schemas.model_routing import (
    LivestockTriageResult,
    ModelCallRecord,
    ModelCostEstimate,
    ModelTokenUsage,
    TriageSlot,
)


def test_livestock_triage_result_is_strict_and_checkpoint_safe() -> None:
    result = LivestockTriageResult(
        intent_candidate="disease_consultation",
        confidence=0.91,
        slots=[
            TriageSlot(
                name="temperature_c",
                value=40.2,
                source_span="40.2°C",
                confidence=0.95,
            )
        ],
        risk_candidate="high",
        risk_signals=["fever"],
    )

    assert LivestockTriageResult.model_validate_json(result.model_dump_json()) == result

    with pytest.raises(ValidationError):
        LivestockTriageResult.model_validate({**result.model_dump(), "diagnosis": "pneumonia"})


def test_livestock_triage_rejects_duplicate_slot_names() -> None:
    with pytest.raises(ValidationError, match="slot names must be unique"):
        LivestockTriageResult(
            intent_candidate="disease_consultation",
            confidence=0.8,
            slots=[
                TriageSlot(name="species", value="calf", source_span="calf", confidence=0.9),
                TriageSlot(name="species", value="cow", source_span="cow", confidence=0.9),
            ],
            risk_candidate="medium",
        )


def test_model_token_usage_distinguishes_measured_from_unavailable() -> None:
    measured = ModelTokenUsage(
        source="provider",
        input_tokens=120,
        output_tokens=30,
        total_tokens=150,
    )
    unavailable = ModelTokenUsage(source="unavailable")

    assert measured.total_tokens == 150
    assert unavailable.input_tokens is None

    with pytest.raises(ValidationError, match="must equal"):
        ModelTokenUsage(source="tokenizer", input_tokens=3, output_tokens=4, total_tokens=8)
    with pytest.raises(ValidationError, match="unavailable usage cannot contain token counts"):
        ModelTokenUsage(source="unavailable", input_tokens=0, output_tokens=0, total_tokens=0)


def test_model_cost_requires_explicit_pricing_snapshot() -> None:
    unconfigured = ModelCostEstimate(pricing_configured=False)
    configured = ModelCostEstimate(
        pricing_configured=True,
        input_usd_per_million_tokens=0.5,
        output_usd_per_million_tokens=1.5,
        input_cost_usd=0.00005,
        output_cost_usd=0.00003,
        total_cost_usd=0.00008,
    )

    assert unconfigured.total_cost_usd is None
    assert configured.total_cost_usd == pytest.approx(0.00008)

    with pytest.raises(ValidationError, match="unconfigured pricing cannot contain costs"):
        ModelCostEstimate(pricing_configured=False, total_cost_usd=0.0)


def test_model_call_record_serializes_usage_without_prompt_content() -> None:
    record = ModelCallRecord(
        operation_key="req-1:triage",
        task_type="livestock_triage",
        provider="transformers",
        model="Qwen/Qwen2.5-0.5B-Instruct",
        selected_model="local_small",
        route_mode="takeover",
        status="success",
        latency_ms=42,
        usage=ModelTokenUsage(source="tokenizer", input_tokens=20, output_tokens=8, total_tokens=28),
        cost=ModelCostEstimate(
            pricing_configured=True,
            input_usd_per_million_tokens=0,
            output_usd_per_million_tokens=0,
            input_cost_usd=0,
            output_cost_usd=0,
            total_cost_usd=0,
        ),
    )

    payload = record.model_dump()
    assert "prompt" not in payload
    assert payload["cost"]["cost_scope"] == "api_token_only"
    assert ModelCallRecord.model_validate(payload) == record


def test_model_call_record_rejects_cost_that_does_not_match_usage() -> None:
    with pytest.raises(ValidationError, match="cost values must match token usage and pricing"):
        ModelCallRecord(
            operation_key="req-1:planning",
            task_type="planning",
            provider="primary",
            model="large-model",
            selected_model="primary",
            route_mode="primary",
            status="success",
            latency_ms=1,
            usage=ModelTokenUsage(source="provider", input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000),
            cost=ModelCostEstimate(
                pricing_configured=True,
                input_usd_per_million_tokens=1.0,
                output_usd_per_million_tokens=2.0,
                input_cost_usd=0.0,
                output_cost_usd=0.0,
                total_cost_usd=0.0,
            ),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TriageSlot(name="temperature_c", value=float("nan"), source_span="40.2", confidence=0.9),
        lambda: ModelCostEstimate(pricing_configured=True, input_usd_per_million_tokens=float("inf"), output_usd_per_million_tokens=0.0),
        lambda: ModelTokenUsage(source="provider", input_tokens=True, output_tokens=1, total_tokens=2),
        lambda: ModelCostEstimate(pricing_configured="false"),
    ],
)
def test_model_routing_schema_rejects_non_finite_or_coerced_values(factory) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_model_call_record_rejects_boolean_latency() -> None:
    with pytest.raises(ValidationError):
        ModelCallRecord(
            operation_key="req-1:usage",
            task_type="livestock_triage",
            provider="mock",
            model="mock",
            selected_model="local_small",
            route_mode="takeover",
            status="success",
            latency_ms=True,
            usage=ModelTokenUsage(source="unavailable"),
            cost=ModelCostEstimate(pricing_configured=False),
        )


def test_model_pricing_settings_reject_negative_rates() -> None:
    settings = Settings(
        model_pricing={
            "primary_input_usd_per_million_tokens": 0.5,
            "primary_output_usd_per_million_tokens": 1.5,
        }
    )

    assert settings.model_pricing.primary_output_usd_per_million_tokens == 1.5
    with pytest.raises(ValidationError):
        Settings(model_pricing={"local_input_usd_per_million_tokens": -1})
    with pytest.raises(ValidationError):
        Settings(model_pricing={"unknown_price": 1.0})
