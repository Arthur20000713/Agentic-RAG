from __future__ import annotations

import asyncio
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
            understanding = DiseaseCaseUnderstanding.model_validate(payload)
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
                "Return one JSON object matching disease_case_understanding. "
                "Use unknown/null when the user did not state a fact. Do not diagnose."
            ),
        )
        return _run_coroutine_sync(self.primary_llm_client.generate_json(request))

    def _prompt(self, state: MultiAgentState) -> str:
        return (
            "Extract structured livestock disease case information from the user message. "
            "Keep source_spans as exact user text fragments.\n"
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
