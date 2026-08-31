from __future__ import annotations

import re

from backend.app.schemas.retrieval import QueryConstraintSnapshot

_SPECIES_TERMS = (
    "犊牛",
    "奶牛",
    "肉牛",
    "羔羊",
    "绵羊",
    "山羊",
    "仔猪",
    "牛",
    "羊",
    "猪",
    "鸡",
    "calf",
    "calves",
    "cattle",
    "cow",
    "heifer",
    "bull",
    "ewe",
    "lamb",
    "sheep",
    "goat",
    "swine",
    "pig",
    "poultry",
)
_NEGATION_TERMS = ("没有", "无", "未", "否认", "并无", "not", "no", "without", "never")
_IDENTIFIER_PATTERN = re.compile(r"\b(?=[A-Za-z0-9_-]*\d)[A-Za-z][A-Za-z0-9_-]{1,31}\b")
_NUMERIC_TEMPORAL_PATTERN = re.compile(
    r"(?:\b\d{4}-\d{1,2}-\d{1,2}\b|"
    r"\d+(?:\.\d+)?\s*(?:mg/kg|kg|g|cm|mm|°?c|度|小时|天|日|周|月|年|"
    r"hours?|days?|weeks?|months?|years?))",
    flags=re.IGNORECASE,
)
_CLAUSE_SPLIT_PATTERN = re.compile(r"[，,；;。.!?？]|\bbut\b|但是|但", flags=re.IGNORECASE)


def extract_query_constraints(query: str) -> QueryConstraintSnapshot:
    text = _normalize_space(query)
    entities = _unique(
        [*_species_entities(text), *_IDENTIFIER_PATTERN.findall(text)]
    )
    numeric_terms = _unique(
        [_normalize_space(match.group(0)) for match in _NUMERIC_TEMPORAL_PATTERN.finditer(text)]
    )
    negated_spans = _unique(
        [
            clause
            for clause in (_normalize_space(item) for item in _CLAUSE_SPLIT_PATTERN.split(text))
            if clause and _negation_markers(clause)
        ]
    )
    return QueryConstraintSnapshot(
        entities=entities,
        numeric_or_temporal_terms=numeric_terms,
        negated_spans=negated_spans,
    )


def semantic_constraint_violations(
    constraints: QueryConstraintSnapshot,
    candidate_queries: list[str],
) -> list[str]:
    combined = _normalize_space(" ".join(candidate_queries))
    combined_folded = combined.casefold()
    violations: list[str] = []

    for entity in constraints.entities:
        if entity.casefold() not in combined_folded:
            violations.append(f"missing_entity:{entity}")
    for term in constraints.numeric_or_temporal_terms:
        if _normalize_space(term).casefold() not in combined_folded:
            violations.append(f"missing_numeric_or_temporal:{term}")
    for span in constraints.negated_spans:
        if _normalize_space(span).casefold() not in combined_folded:
            violations.append(f"missing_negated_span:{span}")

    candidate_constraints = extract_query_constraints(combined)
    protected_entities = {item.casefold() for item in constraints.entities}
    for entity in candidate_constraints.entities:
        if entity.casefold() not in protected_entities:
            violations.append(f"added_entity:{entity}")

    original_markers = {
        marker
        for span in constraints.negated_spans
        for marker in _negation_markers(span)
    }
    for marker in _negation_markers(combined):
        if marker not in original_markers:
            violations.append(f"added_negation:{marker}")
    return _unique(violations)


def _species_entities(text: str) -> list[str]:
    entities: list[str] = []
    folded = text.casefold()
    for term in _SPECIES_TERMS:
        if term.isascii():
            if re.search(rf"\b{re.escape(term)}\b", folded):
                entities.append(term)
        elif term in text:
            entities.append(term)
    return entities


def _negation_markers(text: str) -> set[str]:
    folded = text.casefold()
    markers: set[str] = set()
    for term in _NEGATION_TERMS:
        if term.isascii():
            if re.search(rf"\b{re.escape(term)}\b", folded):
                markers.add(term)
        elif term in text:
            markers.add(term)
    return markers


def _normalize_space(text: str) -> str:
    return " ".join(str(text).strip().split())


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result


__all__ = ["extract_query_constraints", "semantic_constraint_violations"]
