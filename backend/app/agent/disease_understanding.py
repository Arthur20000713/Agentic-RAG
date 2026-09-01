from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.memory_tools import exclude_long_term_memory
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest


class DiseaseCaseUnderstanding(BaseModel):
    status: Literal["success"] = "success"
    schema_name: Literal["disease_case_understanding"] = "disease_case_understanding"
    case_summary: str | None = None
    species: str | None = None
    observed_signs: list[str] = Field(default_factory=list)
    context_factors: list[str] = Field(default_factory=list)
    explicit_user_facts: dict[str, Any] = Field(default_factory=dict)
    information_gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_spans: list[str] = Field(default_factory=list)


class DiseaseUnderstandingAgent:
    def __init__(self, settings: Settings | None = None, primary_llm_client: Any | None = None) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    def run(self, state: MultiAgentState) -> MultiAgentState:
        if not self.settings.disease_llm.enabled:
            return state

        started_at = time.perf_counter()
        key = "disease_understanding_shadow" if self.settings.disease_llm.shadow_mode else "disease_understanding"
        record: dict[str, Any] = {
            "fallback_used": False,
            "fallback_reason": None,
        }
        try:
            payload = self._call_llm(state)
            understanding = DiseaseCaseUnderstanding.model_validate(_normalize_understanding_payload(payload))
            record["understanding"] = understanding.model_dump()
        except ValidationError:
            record["fallback_used"] = True
            record["fallback_reason"] = "schema_validation_failed"
            record["understanding"] = None
        except Exception as exc:
            record["fallback_used"] = True
            record["fallback_reason"] = f"understanding_error:{exc.__class__.__name__}"
            record["understanding"] = None

        state.tool_results[key] = record
        state.agent_trace.append(
            {
                "node": "disease_understanding_agent",
                "status": "fallback" if record["fallback_used"] else "success",
                "shadow_mode": self.settings.disease_llm.shadow_mode,
                "fallback_used": record["fallback_used"],
                "fallback_reason": record["fallback_reason"],
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    def _call_llm(self, state: MultiAgentState) -> dict[str, Any]:
        request = PrimaryLLMRequest(
            prompt=self._prompt(state),
            schema_name="disease_case_understanding",
            context={
                "session_id": state.session_id,
                "normalized_query": state.normalized_query,
                "intent": state.intent,
                "session_context": exclude_long_term_memory(state.session_context),
            },
            system_prompt=(
                "You understand livestock disease consultation messages. "
                "Return exactly one flat JSON object matching disease_case_understanding. "
                "Do not diagnose and do not force a fixed slot list. "
                "Capture all clinically relevant user-stated details as observed_signs, context_factors, "
                "explicit_user_facts, and source_spans. "
                "Use information_gaps only for case-specific details that would materially improve the next answer."
            ),
        )
        return _run_coroutine_sync(self.primary_llm_client.generate_json(request))

    def _prompt(self, state: MultiAgentState) -> str:
        return (
            "Summarize the livestock disease consultation context for retrieval and reasoning. "
            "Keep source_spans as exact user text fragments. "
            "Preserve unusual signs, animal group context, feeding/environment changes, and user negatives. "
            f"User message: {state.normalized_query or state.user_query}"
        )


def _run_coroutine_sync(value: Any) -> dict[str, Any]:
    if not asyncio.iscoroutine(value):
        return dict(value)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)

    result: dict[str, Any] | None = None
    error: BaseException | None = None

    def runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(value)
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if error is not None:
        raise error
    return dict(result or {})


def _normalize_understanding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("disease_case_understanding")
    normalized = dict(payload)
    if isinstance(content, dict):
        normalized.update(content)
        payload = normalized
    if normalized.get("status") != "error":
        normalized["status"] = "success"

    observed_signs = _dedupe(
        _list_field_values(payload.get("observed_signs"))
        or _list_field_values(payload.get("symptoms_normalized"))
        or _list_field_values(payload.get("symptoms"))
        or _list_field_values(payload.get("clinical_signs"))
    )
    context_factors = _dedupe(_list_field_values(payload.get("context_factors")) or _legacy_context_factors(payload))
    explicit_facts = _explicit_user_facts(payload)
    source_spans = _dedupe([*_list_strings(normalized.get("source_spans")), *_collect_source_spans(payload)])

    if observed_signs:
        normalized["observed_signs"] = observed_signs
    if context_factors:
        normalized["context_factors"] = context_factors
    if explicit_facts:
        normalized["explicit_user_facts"] = explicit_facts
    if source_spans:
        normalized["source_spans"] = source_spans

    confidence = _coerce_confidence(normalized.get("confidence"))
    if confidence is not None:
        normalized["confidence"] = confidence

    if not normalized.get("case_summary"):
        normalized["case_summary"] = _build_case_summary(payload, observed_signs, context_factors)
    if normalized.get("species") is not None:
        normalized["species"] = str(normalized["species"])

    for key in ("observed_signs", "context_factors", "information_gaps", "source_spans"):
        if normalized.get(key) is None:
            normalized[key] = []
    if normalized.get("explicit_user_facts") is None:
        normalized["explicit_user_facts"] = {}
    return normalized


def _explicit_user_facts(payload: dict[str, Any]) -> dict[str, Any]:
    facts = payload.get("explicit_user_facts") if isinstance(payload.get("explicit_user_facts"), dict) else {}
    result = dict(facts)
    for key in (
        "species",
        "age_stage",
        "duration_text",
        "duration_days",
        "temperature_c",
        "temperature_status",
        "appetite_status",
        "feces_status",
        "respiratory_status",
        "group_outbreak",
    ):
        value = _field_value(payload, key)
        if value is not None and value != "" and value != []:
            result[key] = value
    return result


def _legacy_context_factors(payload: dict[str, Any]) -> list[str]:
    factors: list[str] = []
    for key in ("age_stage", "appetite_status", "feces_status", "respiratory_status", "temperature_status"):
        value = _field_value(payload, key)
        if value is not None and value != "unknown":
            factors.append(f"{key}: {value}")
    group_outbreak = _field_value(payload, "group_outbreak")
    if group_outbreak is not None:
        factors.append(f"group_outbreak: {group_outbreak}")
    return factors


def _build_case_summary(payload: dict[str, Any], observed_signs: list[str], context_factors: list[str]) -> str | None:
    summary_parts: list[str] = []
    species = _field_value(payload, "species")
    if species and species != "unknown":
        summary_parts.append(f"species: {species}")
    if observed_signs:
        summary_parts.append(f"observed signs: {', '.join(observed_signs)}")
    if context_factors:
        summary_parts.append(f"context: {', '.join(context_factors)}")
    return "; ".join(summary_parts) if summary_parts else None


def _field_value(payload: dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _list_field_values(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    values: list[str] = []
    for item in items:
        item_value = item.get("value") if isinstance(item, dict) else item
        if item_value is not None:
            values.append(str(item_value))
    return _dedupe(values)


def _list_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return _dedupe([item for item in value.values() if isinstance(item, str)])
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("source_span")
                if isinstance(text, str):
                    values.append(text)
        return _dedupe(values)
    return []


def _collect_source_spans(value: Any) -> list[str]:
    spans: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.endswith("_span") and isinstance(nested, str):
                spans.append(nested)
            spans.extend(_collect_source_spans(nested))
    elif isinstance(value, list):
        for item in value:
            spans.extend(_collect_source_spans(item))
    return _dedupe(spans)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _coerce_confidence(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized == "high":
        return 0.85
    if normalized == "medium":
        return 0.55
    if normalized == "low":
        return 0.25
    try:
        return max(0.0, min(1.0, float(normalized)))
    except ValueError:
        return None
