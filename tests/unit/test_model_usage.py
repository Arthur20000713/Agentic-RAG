from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.model.usage import (
    append_model_call_records,
    chat_completions_usage,
    model_cost_estimate,
    ollama_usage,
    summarize_model_calls,
    tokenizer_usage,
)
from backend.app.schemas.model_routing import ModelCallRecord, ModelTokenUsage


def test_provider_and_tokenizer_usage_preserve_measured_source() -> None:
    assert chat_completions_usage(
        {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    ) == ModelTokenUsage(source="provider", input_tokens=120, output_tokens=30, total_tokens=150)
    assert ollama_usage({"prompt_eval_count": 20, "eval_count": 5}) == ModelTokenUsage(
        source="provider", input_tokens=20, output_tokens=5, total_tokens=25
    )
    assert tokenizer_usage(8, 3) == ModelTokenUsage(
        source="tokenizer", input_tokens=8, output_tokens=3, total_tokens=11
    )


def test_invalid_or_missing_usage_is_unavailable_instead_of_zero() -> None:
    for usage in (
        chat_completions_usage(None),
        chat_completions_usage({"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 99}),
        ollama_usage({"prompt_eval_count": True, "eval_count": 1}),
        tokenizer_usage(-1, 2),
    ):
        assert usage == ModelTokenUsage(source="unavailable")


def test_cost_uses_pricing_snapshot_and_keeps_unconfigured_cost_null() -> None:
    usage = ModelTokenUsage(source="provider", input_tokens=1_000_000, output_tokens=500_000, total_tokens=1_500_000)
    configured = Settings(
        model_pricing={
            "primary_input_usd_per_million_tokens": 2.0,
            "primary_output_usd_per_million_tokens": 6.0,
        }
    )

    cost = model_cost_estimate(configured, "primary", usage)

    assert cost.input_cost_usd == 2.0
    assert cost.output_cost_usd == 3.0
    assert cost.total_cost_usd == 5.0
    assert cost.cost_scope == "api_token_only"
    assert model_cost_estimate(Settings(), "primary", usage).model_dump() == {
        "pricing_configured": False,
        "cost_scope": "api_token_only",
        "input_usd_per_million_tokens": None,
        "output_usd_per_million_tokens": None,
        "input_cost_usd": None,
        "output_cost_usd": None,
        "total_cost_usd": None,
    }
    local_cost = model_cost_estimate(Settings(), "local_small", usage)
    assert local_cost.pricing_configured is True
    assert local_cost.total_cost_usd == 0.0
    assert local_cost.cost_scope == "api_token_only"


def test_summary_marks_partial_tokens_and_cost_without_hiding_known_subtotals() -> None:
    measured = _record("turn:triage", ModelTokenUsage(source="provider", input_tokens=10, output_tokens=2, total_tokens=12))
    unavailable = _record("turn:planner", ModelTokenUsage(source="unavailable"))
    records: list[ModelCallRecord] = []

    append_model_call_records(records, [measured, measured, unavailable])
    summary = summarize_model_calls(records)

    assert [record.operation_key for record in records] == ["turn:triage", "turn:planner"]
    assert summary["call_count"] == 2
    assert summary["known_total_tokens"] == 12
    assert summary["total_tokens"] is None
    assert summary["tokens_complete"] is False
    assert summary["total_cost_usd"] is None
    assert summary["cost_scope"] == "api_token_only"
    serialized = str([record.model_dump(mode="json") for record in records]) + str(summary)
    for sensitive in ("prompt", "Authorization", "api_key", "long_term_memory", "chain-of-thought"):
        assert sensitive not in serialized


def _record(operation_key: str, usage: ModelTokenUsage) -> ModelCallRecord:
    settings = Settings()
    return ModelCallRecord(
        operation_key=operation_key,
        task_type="reasoning",
        provider="test",
        model="test-model",
        selected_model="primary",
        route_mode="primary",
        status="success",
        latency_ms=3,
        usage=usage,
        cost=model_cost_estimate(settings, "primary", usage),
    )
