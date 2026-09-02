from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from backend.app.core.config import Settings
from backend.app.schemas.model_routing import (
    ModelCallRecord,
    ModelCallStatus,
    ModelCostEstimate,
    ModelName,
    ModelRouteMode,
    ModelTaskType,
    ModelTokenUsage,
)

MAX_MODEL_CALL_RECORDS = 64

_TASK_BY_SCHEMA: dict[str, ModelTaskType] = {
    "direct_answer_draft": "final_answer",
    "disease_case_understanding": "reasoning",
    "disease_reasoning": "reasoning",
    "final_answer": "final_answer",
    "grounded_rag_answer": "final_answer",
    "intent_routing": "intent_routing",
    "livestock_triage": "livestock_triage",
    "measurement_formatting": "measurement_analysis",
    "planning": "planning",
    "query_normalization": "query_normalization",
    "reasoning": "reasoning",
    "reference_only_answer": "final_answer",
    "retrieval_decomposition": "reasoning",
    "retrieval_rewrite": "reasoning",
    "slot_extraction": "structured_extraction",
    "summarization": "summarization",
    "task_plan": "planning",
}


def unavailable_usage() -> ModelTokenUsage:
    return ModelTokenUsage(source="unavailable")


def chat_completions_usage(raw: Any) -> ModelTokenUsage:
    if not isinstance(raw, dict):
        return unavailable_usage()
    return _measured_usage(
        raw.get("prompt_tokens"),
        raw.get("completion_tokens"),
        raw.get("total_tokens"),
        source="provider",
    )


def ollama_usage(raw: Any) -> ModelTokenUsage:
    if not isinstance(raw, dict):
        return unavailable_usage()
    return _measured_usage(
        raw.get("prompt_eval_count"),
        raw.get("eval_count"),
        None,
        source="provider",
    )


def tokenizer_usage(input_tokens: Any, output_tokens: Any) -> ModelTokenUsage:
    return _measured_usage(input_tokens, output_tokens, None, source="tokenizer")


def model_cost_estimate(
    settings: Settings,
    selected_model: ModelName,
    usage: ModelTokenUsage,
) -> ModelCostEstimate:
    pricing = settings.model_pricing
    if selected_model == "primary":
        input_rate = pricing.primary_input_usd_per_million_tokens
        output_rate = pricing.primary_output_usd_per_million_tokens
    else:
        input_rate = pricing.local_input_usd_per_million_tokens
        output_rate = pricing.local_output_usd_per_million_tokens

    if input_rate is None or output_rate is None:
        return ModelCostEstimate(pricing_configured=False)

    rates = {
        "input_usd_per_million_tokens": float(input_rate),
        "output_usd_per_million_tokens": float(output_rate),
    }
    if usage.source == "unavailable":
        return ModelCostEstimate(pricing_configured=True, **rates)

    input_cost = usage.input_tokens * float(input_rate) / 1_000_000  # type: ignore[operator]
    output_cost = usage.output_tokens * float(output_rate) / 1_000_000  # type: ignore[operator]
    return ModelCostEstimate(
        pricing_configured=True,
        **rates,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + output_cost,
    )


class ModelCallRecorder:
    """Collect compact call records without retaining prompts or provider responses."""

    def __init__(self, settings: Settings, selected_model: ModelName) -> None:
        self.settings = settings
        self.selected_model = selected_model
        self._records: list[ModelCallRecord] = []
        self._scope_prefix = "standalone"
        self._scope_index = 0

    @contextmanager
    def scope(self, operation_prefix: str) -> Iterator[None]:
        previous = (self._scope_prefix, self._scope_index)
        self._scope_prefix = operation_prefix[:180]
        self._scope_index = 0
        try:
            yield
        finally:
            self._scope_prefix, self._scope_index = previous

    def record(
        self,
        *,
        schema_name: str,
        provider: str,
        model: str,
        status: ModelCallStatus,
        latency_ms: int,
        usage: ModelTokenUsage,
        fallback_reason: str | None = None,
    ) -> ModelCallRecord:
        self._scope_index += 1
        normalized_schema = schema_name.strip().lower()
        task_type = _TASK_BY_SCHEMA.get(normalized_schema, "reasoning")
        record = ModelCallRecord(
            operation_key=(
                f"{self._scope_prefix}:{normalized_schema}:{self._scope_index}"
            )[:256],
            task_type=task_type,
            provider=(provider or "unknown")[:64],
            model=(model or "unknown")[:200],
            selected_model=self.selected_model,
            route_mode=_route_mode(self.settings, self.selected_model),
            status=status,
            fallback_reason=(fallback_reason[:160] if fallback_reason else None),
            latency_ms=max(0, int(latency_ms)),
            usage=usage,
            cost=model_cost_estimate(self.settings, self.selected_model, usage),
        )
        self._records.append(record)
        return record

    def drain(self) -> list[ModelCallRecord]:
        records = self._records
        self._records = []
        return records


def append_model_call_records(
    existing: list[ModelCallRecord],
    incoming: Sequence[ModelCallRecord],
) -> None:
    keys = {record.operation_key for record in existing}
    for record in incoming:
        if record.operation_key in keys or len(existing) >= MAX_MODEL_CALL_RECORDS:
            continue
        existing.append(record)
        keys.add(record.operation_key)


def summarize_model_calls(records: Sequence[ModelCallRecord]) -> dict[str, Any]:
    unavailable = sum(record.usage.source == "unavailable" for record in records)
    unpriced = sum(
        not record.cost.pricing_configured or record.cost.total_cost_usd is None
        for record in records
    )
    known_input = sum(record.usage.input_tokens or 0 for record in records)
    known_output = sum(record.usage.output_tokens or 0 for record in records)
    known_total = sum(record.usage.total_tokens or 0 for record in records)
    known_cost = sum(record.cost.total_cost_usd or 0.0 for record in records)
    return {
        "call_count": len(records),
        "status_counts": _counts(record.status for record in records),
        "model_counts": _counts(record.selected_model for record in records),
        "usage_source_counts": _counts(record.usage.source for record in records),
        "total_latency_ms": sum(record.latency_ms for record in records),
        "known_input_tokens": known_input,
        "known_output_tokens": known_output,
        "known_total_tokens": known_total,
        "tokens_complete": unavailable == 0,
        "input_tokens": known_input if unavailable == 0 else None,
        "output_tokens": known_output if unavailable == 0 else None,
        "total_tokens": known_total if unavailable == 0 else None,
        "known_total_cost_usd": known_cost,
        "cost_complete": unpriced == 0,
        "total_cost_usd": known_cost if unpriced == 0 else None,
        "cost_scope": "api_token_only",
    }


def _measured_usage(
    input_tokens: Any,
    output_tokens: Any,
    total_tokens: Any,
    *,
    source: str,
) -> ModelTokenUsage:
    if not _valid_count(input_tokens) or not _valid_count(output_tokens):
        return unavailable_usage()
    expected_total = input_tokens + output_tokens
    if total_tokens is not None and (
        not _valid_count(total_tokens) or total_tokens != expected_total
    ):
        return unavailable_usage()
    return ModelTokenUsage(
        source=source,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=expected_total,
    )


def _valid_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _route_mode(settings: Settings, selected_model: ModelName) -> ModelRouteMode:
    if not settings.model_router.enabled:
        return "disabled"
    if settings.model_router.shadow_mode:
        return "shadow"
    return "takeover" if selected_model == "local_small" else "primary"


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result


__all__ = [
    "MAX_MODEL_CALL_RECORDS",
    "ModelCallRecorder",
    "append_model_call_records",
    "chat_completions_usage",
    "model_cost_estimate",
    "ollama_usage",
    "summarize_model_calls",
    "tokenizer_usage",
    "unavailable_usage",
]
