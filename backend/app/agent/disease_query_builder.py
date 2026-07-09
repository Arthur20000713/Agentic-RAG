from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.agent.state import MultiAgentState


@dataclass(frozen=True)
class DiseaseRagQuery:
    query: str
    facts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class DiseaseQueryBuilder:
    def build(self, state: MultiAgentState) -> DiseaseRagQuery:
        facts = self._facts(state)
        parts = [
            "livestock disease consultation",
            "evidence-based contributing factors",
            "safe actions",
            "vet escalation triggers",
            state.normalized_query or state.user_query,
        ]
        parts.extend(self._fact_terms(facts))
        query = " ".join(_dedupe([_compact(part) for part in parts if _compact(part)]))
        warnings = [] if facts else ["disease_query_used_raw_user_message_only"]
        return DiseaseRagQuery(query=query, facts=facts, warnings=warnings)

    def _facts(self, state: MultiAgentState) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        self._merge_session_context(facts, state.session_context)
        self._merge_understanding(facts, self._understanding(state))
        return facts

    def _merge_session_context(self, facts: dict[str, Any], session_context: dict[str, Any]) -> None:
        if isinstance(session_context.get("last_understanding"), dict):
            self._merge_understanding(facts, session_context["last_understanding"])
        confirmed = session_context.get("confirmed_case_fields")
        if isinstance(confirmed, dict):
            facts.setdefault("session_context", confirmed)

    def _merge_understanding(self, facts: dict[str, Any], understanding: dict[str, Any]) -> None:
        if not understanding:
            return
        for key in ("case_summary", "species", "observed_signs", "context_factors", "explicit_user_facts", "information_gaps"):
            value = understanding.get(key)
            if value not in (None, "", [], {}):
                facts[key] = value

    def _understanding(self, state: MultiAgentState) -> dict[str, Any]:
        for key in ("disease_understanding", "disease_understanding_shadow"):
            record = state.tool_results.get(key)
            if isinstance(record, dict) and isinstance(record.get("understanding"), dict):
                return dict(record["understanding"])
        return {}

    def _fact_terms(self, facts: dict[str, Any]) -> list[str]:
        terms: list[str] = []
        for key in ("case_summary", "species"):
            value = facts.get(key)
            if isinstance(value, str):
                terms.append(value)
        for key in ("observed_signs", "context_factors", "information_gaps"):
            value = facts.get(key)
            if isinstance(value, list):
                terms.extend(str(item) for item in value)
        for key in ("explicit_user_facts", "session_context"):
            value = facts.get(key)
            if isinstance(value, dict):
                terms.extend(_flatten_dict_terms(value))
        return terms


def _flatten_dict_terms(value: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key, item in value.items():
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            terms.extend(_flatten_dict_terms(item))
        elif isinstance(item, list):
            terms.extend(str(nested) for nested in item if str(nested).strip())
        else:
            terms.append(f"{key}: {item}")
    return terms


def _compact(value: str) -> str:
    return " ".join(value.split())


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
