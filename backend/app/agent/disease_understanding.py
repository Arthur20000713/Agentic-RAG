from __future__ import annotations

import asyncio
import re
import threading
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.extractor import DiseaseSlots
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest


Species = Literal["cattle", "sheep", "pig", "unknown"]
TemperatureStatus = Literal["normal", "fever", "low", "unknown"]
AppetiteStatus = Literal["normal", "reduced", "none", "unknown"]


class DiseaseCaseUnderstanding(BaseModel):
    status: Literal["success"] = "success"
    schema_name: Literal["disease_case_understanding"] = "disease_case_understanding"
    species: Species = "unknown"
    age_stage: str | None = None
    symptoms_raw: list[str] = Field(default_factory=list)
    symptoms_normalized: list[str] = Field(default_factory=list)
    duration_text: str | None = None
    duration_days: float | None = Field(default=None, ge=0)
    temperature_c: float | None = Field(default=None, ge=30, le=45)
    temperature_status: TemperatureStatus = "unknown"
    appetite_status: AppetiteStatus = "unknown"
    feces_status: str | None = None
    respiratory_status: str | None = None
    group_outbreak: bool | None = None
    severity_signals: list[str] = Field(default_factory=list)
    missing_critical_info: list[str] = Field(default_factory=list)
    answered_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_spans: list[str] = Field(default_factory=list)


def slots_from_understanding(
    understanding: DiseaseCaseUnderstanding,
    *,
    fallback_slots: DiseaseSlots | None = None,
) -> DiseaseSlots:
    fallback_slots = fallback_slots or DiseaseSlots()
    species = None if understanding.species == "unknown" else understanding.species
    symptoms = _dedupe([*understanding.symptoms_normalized, *fallback_slots.symptoms])
    return DiseaseSlots(
        species=species or fallback_slots.species,
        age_stage=understanding.age_stage or fallback_slots.age_stage,
        symptoms=symptoms,
        temperature_c=understanding.temperature_c if understanding.temperature_c is not None else fallback_slots.temperature_c,
        duration_days=understanding.duration_days if understanding.duration_days is not None else fallback_slots.duration_days,
        group_outbreak=understanding.group_outbreak
        if understanding.group_outbreak is not None
        else fallback_slots.group_outbreak,
    )


class DiseaseUnderstandingAgent:
    def __init__(self, settings: Settings | None = None, primary_llm_client: Any | None = None) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    def run(self, state: MultiAgentState, *, rule_slots: DiseaseSlots) -> MultiAgentState:
        if not self.settings.disease_llm.enabled:
            return state

        started_at = time.perf_counter()
        payload = self._call_llm(state)
        key = "disease_understanding_shadow" if self.settings.disease_llm.shadow_mode else "disease_understanding"
        record: dict[str, Any] = {
            "fallback_used": False,
            "fallback_reason": None,
            "rule_slots": rule_slots.model_dump(),
        }
        try:
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
                "session_context": state.session_context,
            },
            system_prompt=(
                "You extract livestock disease consultation facts. "
                "Return exactly one flat JSON object matching disease_case_understanding; do not wrap it. "
                "Required keys: status, schema_name, species, age_stage, symptoms_raw, symptoms_normalized, "
                "duration_text, duration_days, temperature_c, temperature_status, appetite_status, feces_status, "
                "respiratory_status, group_outbreak, severity_signals, missing_critical_info, answered_questions, "
                "confidence, source_spans. species must be one of cattle, sheep, pig, unknown. "
                "Map cow/calf/bovine and Chinese cattle terms to cattle; lamb/ovine to sheep; swine/porcine to pig. "
                "temperature_status must be normal, fever, low, or unknown; use fever for high temperatures. "
                "appetite_status must be normal, reduced, none, or unknown. "
                "Use numbers for duration_days and temperature_c. Use unknown/null when the user did not state a fact. "
                "Do not diagnose."
            ),
        )
        return _run_coroutine_sync(self.primary_llm_client.generate_json(request))

    def _prompt(self, state: MultiAgentState) -> str:
        return (
            "Extract structured livestock disease case information from the user message. "
            "Keep source_spans as exact user text fragments. "
            "If the user mentions similar animals in the herd, set group_outbreak=true. "
            "If the user mentions reduced feed intake, set appetite_status=reduced.\n"
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


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _normalize_understanding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("disease_case_understanding")
    normalized = dict(payload)
    if isinstance(content, dict):
        normalized.update(content)
        payload = normalized
    if normalized.get("status") != "error":
        normalized["status"] = "success"
    source_spans = _dedupe([*_list_strings(normalized.get("source_spans")), *_collect_source_spans(payload)])
    if source_spans:
        normalized["source_spans"] = source_spans

    confidence = _coerce_confidence(normalized.get("confidence"))
    if confidence is not None:
        normalized["confidence"] = confidence

    species = _coerce_species(_field_value(payload, "species"))
    if species:
        normalized["species"] = species

    age_stage = _field_value(payload, "age_stage") or _field_value(payload, "age")
    if age_stage is not None:
        normalized["age_stage"] = str(age_stage)

    symptoms = (
        _list_field_values(payload.get("symptoms_normalized"))
        or _list_field_values(payload.get("symptoms"))
        or _list_field_values(payload.get("clinical_signs"))
    )
    if symptoms:
        normalized["symptoms_raw"] = _list_field_values(payload.get("symptoms_raw")) or symptoms
        normalized["symptoms_normalized"] = symptoms

    duration = payload.get("duration")
    duration_text = _field_value(payload, "duration_text") or _field_value(payload, "duration")
    if duration_text is not None:
        normalized["duration_text"] = str(duration_text)
    duration_days = _field_value(payload, "duration_days")
    if duration_days is None and isinstance(duration, dict):
        duration_days = duration.get("days") or duration.get("duration_days")
    if duration_days is None and isinstance(duration, (int, float, str)):
        duration_days = duration
    if duration_days is not None:
        parsed_duration_days = _coerce_number(duration_days)
        if parsed_duration_days is not None:
            normalized["duration_days"] = parsed_duration_days

    temperature = payload.get("temperature")
    temperature_c = _field_value(payload, "temperature_c")
    if temperature_c is None and isinstance(temperature, dict):
        temperature_c = temperature.get("temperature_c") or temperature.get("celsius") or temperature.get("value")
    if temperature_c is None and isinstance(temperature, (int, float, str)):
        temperature_c = temperature
    if temperature_c is None:
        temperature_c = _field_value(payload, "fever_temperature")
    if temperature_c is not None:
        parsed_temperature_c = _coerce_number(temperature_c)
        if parsed_temperature_c is not None:
            normalized["temperature_c"] = parsed_temperature_c
            temperature_c = parsed_temperature_c

    temperature_status = _coerce_temperature_status(
        _field_value(payload, "temperature_status")
        or (temperature.get("status") if isinstance(temperature, dict) else None),
        temperature_c,
    )
    if temperature_status:
        normalized["temperature_status"] = temperature_status

    appetite_status = _coerce_appetite_status(
        _field_value(payload, "appetite_status")
        or _field_value(payload, "appetite")
        or _field_value(payload, "feed_intake_change")
    )
    if appetite_status is None:
        appetite_status = _appetite_status_from_symptoms(symptoms)
    if appetite_status:
        normalized["appetite_status"] = appetite_status

    group_outbreak = _field_value(payload, "group_outbreak")
    if group_outbreak is None:
        group_outbreak = _group_outbreak_from_count(_field_value(payload, "number_sick"))
    if group_outbreak is None:
        group_outbreak = _group_outbreak_from_count(_field_value(payload, "similar_cases_count"))
    if group_outbreak is None:
        group_outbreak = _group_outbreak_from_count(_field_value(payload, "similar_cases"))
    if group_outbreak is None:
        group_outbreak = _group_outbreak_from_count(_field_value(payload, "herd_similar_count"))
    if group_outbreak is not None:
        normalized["group_outbreak"] = group_outbreak

    for key in ("symptoms_raw", "symptoms_normalized", "severity_signals", "missing_critical_info", "answered_questions"):
        if normalized.get(key) is None:
            normalized[key] = []
    return normalized


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


def _coerce_species(value: Any) -> Species | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"cattle", "cow", "calf", "bovine"}:
        return "cattle"
    if any(token in normalized for token in {"\u725b", "\u5c0f\u725b", "\u728a\u725b"}):
        return "cattle"
    if normalized in {"sheep", "lamb", "ovine"}:
        return "sheep"
    if "\u7f8a" in normalized:
        return "sheep"
    if normalized in {"pig", "swine", "porcine", "hog"}:
        return "pig"
    if "\u732a" in normalized:
        return "pig"
    if normalized in {"unknown", "unclear", "not specified"}:
        return "unknown"
    return None


def _coerce_temperature_status(value: Any, temperature_c: Any) -> TemperatureStatus | None:
    if value is not None:
        normalized = str(value).strip().lower()
        if normalized in {"normal", "fever", "low", "unknown"}:
            return normalized  # type: ignore[return-value]
        if normalized in {"high", "elevated", "febrile"}:
            return "fever"
    try:
        numeric_temperature = float(temperature_c)
    except (TypeError, ValueError):
        return None
    if numeric_temperature >= 39.5:
        return "fever"
    if numeric_temperature < 37.0:
        return "low"
    return "normal"


def _coerce_appetite_status(value: Any) -> AppetiteStatus | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"normal", "reduced", "none", "unknown"}:
        return normalized  # type: ignore[return-value]
    if normalized in {"low", "decreased", "poor", "reduced feed intake", "less"}:
        return "reduced"
    if any(token in normalized for token in {"\u4e0b\u964d", "\u51cf\u5c11", "\u5dee"}):
        return "reduced"
    if normalized in {"no", "absent", "not eating", "anorexia"}:
        return "none"
    return None


def _appetite_status_from_symptoms(symptoms: list[str]) -> AppetiteStatus | None:
    for symptom in symptoms:
        status = _coerce_appetite_status(symptom)
        if status is not None:
            return status
    return None


def _group_outbreak_from_count(value: Any) -> bool | None:
    number = _coerce_number(value)
    return number > 1 if number is not None else None


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def _coerce_confidence(value: Any) -> float | None:
    number = _coerce_number(value)
    if number is not None:
        return max(0.0, min(1.0, number))
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized == "high":
        return 0.85
    if normalized == "medium":
        return 0.55
    if normalized == "low":
        return 0.25
    return None
