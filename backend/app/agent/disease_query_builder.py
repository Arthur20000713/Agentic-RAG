from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.agent.state import MultiAgentState


DIAGNOSIS_KEYS = {
    "diagnosis",
    "likely_diagnosis",
    "suspected_disease",
    "suspected_diseases",
    "possible_diagnoses",
}


@dataclass(frozen=True)
class DiseaseRagQuery:
    query: str
    facts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class DiseaseQueryBuilder:
    def build(self, state: MultiAgentState) -> DiseaseRagQuery:
        facts = self._facts(state)
        terms = ["livestock disease consultation", "evidence-based guidance", "safe actions", "vet triggers"]
        if species := facts.get("species"):
            terms.append(str(species))
        for symptom in facts.get("symptoms") or []:
            terms.append(str(symptom))
        for field in ("duration_days", "temperature_c", "temperature_status", "group_outbreak"):
            if field in facts and facts[field] is not None:
                terms.append(f"{field}:{self._format_value(facts[field])}")
        return DiseaseRagQuery(query=" ".join(terms), facts=facts)

    def _facts(self, state: MultiAgentState) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        self._merge_confirmed_fields(facts, state.session_context)
        self._merge_slots(facts, state.extracted_slots)
        self._merge_understanding(facts, self._understanding(state))
        return facts

    def _merge_confirmed_fields(self, facts: dict[str, Any], session_context: dict[str, Any]) -> None:
        confirmed = session_context.get("confirmed_case_fields")
        if isinstance(confirmed, dict):
            self._merge_slots(facts, confirmed)

    def _merge_slots(self, facts: dict[str, Any], slots: dict[str, Any]) -> None:
        for field in ("species", "duration_days", "temperature_c", "group_outbreak"):
            value = slots.get(field)
            if value is not None:
                facts[field] = value
        symptoms = slots.get("symptoms")
        if isinstance(symptoms, list) and symptoms:
            facts["symptoms"] = list(symptoms)

    def _merge_understanding(self, facts: dict[str, Any], understanding: dict[str, Any]) -> None:
        if not understanding:
            return
        for field in DIAGNOSIS_KEYS:
            understanding.pop(field, None)
        species = understanding.get("species")
        if species and species != "unknown" and not facts.get("species"):
            facts["species"] = species
        symptoms = understanding.get("symptoms_normalized")
        if isinstance(symptoms, list) and symptoms and not facts.get("symptoms"):
            facts["symptoms"] = list(symptoms)
        temperature_status = understanding.get("temperature_status")
        if temperature_status and temperature_status != "unknown" and not facts.get("temperature_c"):
            facts["temperature_status"] = temperature_status
        if understanding.get("group_outbreak") is not None and "group_outbreak" not in facts:
            facts["group_outbreak"] = understanding["group_outbreak"]

    def _understanding(self, state: MultiAgentState) -> dict[str, Any]:
        for key in ("disease_understanding", "disease_understanding_shadow"):
            record = state.tool_results.get(key)
            if isinstance(record, dict) and isinstance(record.get("understanding"), dict):
                return dict(record["understanding"])
        return {}

    def _format_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
