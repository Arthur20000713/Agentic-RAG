from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.app.agent.query_constraints import (
    extract_query_constraints,
    semantic_constraint_violations,
)
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest
from backend.app.schemas.retrieval import (
    MAX_PRIMARY_SUBQUERIES,
    MAX_RETRIEVAL_QUERY_LENGTH,
    QueryConstraintSnapshot,
    RetrievalQuery,
)

_MODEL_METADATA_FIELDS = {
    "error_code",
    "fallback_required",
    "latency_ms",
    "model",
    "provider",
    "reason",
    "schema_name",
    "status",
}
_DIAGNOSIS_TERMS = (
    "肺炎",
    "乳房炎",
    "口蹄疫",
    "布鲁氏菌病",
    "pneumonia",
    "mastitis",
    "foot-and-mouth disease",
    "brucellosis",
)


class _DecompositionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_RETRIEVAL_QUERY_LENGTH)
    purpose: str = Field(min_length=1, max_length=200)


class _DecompositionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[_DecompositionCandidate] = Field(
        min_length=1,
        max_length=MAX_PRIMARY_SUBQUERIES,
    )

    @model_validator(mode="after")
    def validate_unique_queries(self) -> _DecompositionPayload:
        keys = [_query_key(item.text) for item in self.queries]
        if len(set(keys)) != len(keys):
            raise ValueError("decomposed queries must be unique")
        return self


class _RewritePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=MAX_RETRIEVAL_QUERY_LENGTH)
    purpose: str = Field(min_length=1, max_length=200)


@dataclass(frozen=True)
class DecompositionOutcome:
    queries: list[RetrievalQuery]
    source: str
    fallback_used: bool
    fallback_reason: str | None = None
    rejection_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RewriteOutcome:
    query: RetrievalQuery | None
    source: str
    fallback_used: bool
    fallback_reason: str | None = None
    rejection_reasons: list[str] = field(default_factory=list)


class QueryDecomposer:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        primary_llm_client: Any | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    async def decompose(self, original_query: str) -> DecompositionOutcome:
        original = original_query.strip()
        if not original or len(original) > MAX_RETRIEVAL_QUERY_LENGTH:
            raise ValueError("original query length is outside the retrieval limit")
        if not self.settings.primary_llm.enabled:
            return self._fallback(original, "primary_llm_disabled")

        try:
            raw = await self.primary_llm_client.generate_json(self._request(original))
        except Exception as exc:  # noqa: BLE001 - model failures use the safe original-query fallback
            return self._fallback(original, f"decomposer_error:{exc.__class__.__name__}")
        model_failure = _model_failure_reason(raw)
        if model_failure is not None:
            return self._fallback(original, model_failure)

        try:
            payload = _DecompositionPayload.model_validate(
                _body(raw, {"queries"})
            )
        except (TypeError, ValidationError, ValueError):
            return self._fallback(original, "schema_validation_failed")

        candidate_texts = [candidate.text.strip() for candidate in payload.queries]
        constraints = extract_query_constraints(original)
        violations = semantic_constraint_violations(constraints, candidate_texts)
        violations.extend(_added_diagnoses(original, " ".join(candidate_texts)))
        if violations:
            return self._fallback(
                original,
                "semantic_constraint_violation",
                rejection_reasons=_unique(violations),
            )

        queries = [
            RetrievalQuery(
                query_id=f"q_primary_{index}",
                text=candidate.text.strip(),
                origin=(
                    "original"
                    if len(payload.queries) == 1
                    and _query_key(candidate.text) == _query_key(original)
                    else "decomposed"
                ),
                purpose=candidate.purpose.strip(),
            )
            for index, candidate in enumerate(payload.queries, start=1)
        ]
        return DecompositionOutcome(
            queries=queries,
            source="model",
            fallback_used=False,
        )

    def _fallback(
        self,
        original_query: str,
        reason: str,
        *,
        rejection_reasons: list[str] | None = None,
    ) -> DecompositionOutcome:
        return DecompositionOutcome(
            queries=[
                RetrievalQuery(
                    query_id="q_primary_1",
                    text=original_query,
                    origin="original",
                    purpose="retrieve the original trusted query",
                )
            ],
            source="original",
            fallback_used=True,
            fallback_reason=reason,
            rejection_reasons=rejection_reasons or [],
        )

    def _request(self, original_query: str) -> PrimaryLLMRequest:
        return PrimaryLLMRequest(
            prompt="Decompose the trusted livestock query into the smallest useful retrieval queries.",
            schema_name="retrieval_decomposition",
            context={"original_query": original_query},
            system_prompt=(
                "Return exactly one JSON object with queries containing one to three objects with text "
                "and purpose. Preserve every animal, entity ID, number, time expression, and negated "
                "statement. Do not add diagnoses or control tools, collection, top_k, providers, or calls."
            ),
        )


class QueryRewriteGuard:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        primary_llm_client: Any | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    async def rewrite(
        self,
        *,
        original_query: str,
        constraints: QueryConstraintSnapshot,
        missing_aspects: list[str],
        previous_queries: list[tuple[str, str]],
    ) -> RewriteOutcome:
        original = original_query.strip()
        aspects = _unique([item.strip() for item in missing_aspects if item.strip()])[
            :MAX_PRIMARY_SUBQUERIES
        ]
        parent_ids = _unique([query_id for query_id, _ in previous_queries])[
            :MAX_PRIMARY_SUBQUERIES
        ]
        if (
            not original
            or len(original) > MAX_RETRIEVAL_QUERY_LENGTH
            or not aspects
            or any(len(aspect) > 100 for aspect in aspects)
            or not parent_ids
        ):
            return RewriteOutcome(
                query=None,
                source="rejected",
                fallback_used=False,
                rejection_reasons=["missing_rewrite_inputs"],
            )

        fallback_reason: str | None = None
        if not self.settings.primary_llm.enabled:
            candidate_text = f"{original} {'; '.join(aspects)}"
            purpose = "fill missing evidence"
            source = "deterministic"
            fallback_reason = "primary_llm_disabled"
        else:
            try:
                raw = await self.primary_llm_client.generate_json(self._request(original, aspects))
            except Exception as exc:  # noqa: BLE001 - model failures use a guarded deterministic rewrite
                fallback_reason = f"rewriter_error:{exc.__class__.__name__}"
            else:
                fallback_reason = _model_failure_reason(raw)
                if fallback_reason is None:
                    try:
                        payload = _RewritePayload.model_validate(
                            _body(raw, {"query", "purpose"})
                        )
                    except (TypeError, ValidationError, ValueError):
                        fallback_reason = "schema_validation_failed"
                    else:
                        candidate_text = payload.query.strip()
                        purpose = payload.purpose.strip()
                        source = "model"

            if fallback_reason is not None:
                candidate_text = f"{original} {'; '.join(aspects)}"
                purpose = "fill missing evidence"
                source = "deterministic"

        if len(candidate_text) > MAX_RETRIEVAL_QUERY_LENGTH:
            return RewriteOutcome(
                query=None,
                source="rejected",
                fallback_used=fallback_reason is not None,
                fallback_reason=fallback_reason,
                rejection_reasons=["query_length_exceeded"],
            )

        historical_keys = {_query_key(text) for _, text in previous_queries}
        if _query_key(candidate_text) in historical_keys:
            return RewriteOutcome(
                query=None,
                source="rejected",
                fallback_used=fallback_reason is not None,
                fallback_reason=fallback_reason,
                rejection_reasons=["duplicate_query"],
            )

        violations = semantic_constraint_violations(constraints, [candidate_text])
        if violations:
            return RewriteOutcome(
                query=None,
                source="rejected",
                fallback_used=fallback_reason is not None,
                fallback_reason=fallback_reason,
                rejection_reasons=["semantic_constraint_violation", *_unique(violations)],
            )
        diagnoses = _added_diagnoses(original, candidate_text)
        if diagnoses:
            return RewriteOutcome(
                query=None,
                source="rejected",
                fallback_used=fallback_reason is not None,
                fallback_reason=fallback_reason,
                rejection_reasons=diagnoses,
            )

        return RewriteOutcome(
            query=RetrievalQuery(
                query_id="q_secondary",
                text=candidate_text,
                origin="secondary",
                purpose=purpose,
                parent_query_ids=parent_ids,
            ),
            source=source,
            fallback_used=fallback_reason is not None,
            fallback_reason=fallback_reason,
        )

    def _request(self, original_query: str, missing_aspects: list[str]) -> PrimaryLLMRequest:
        return PrimaryLLMRequest(
            prompt="Write one secondary retrieval query that fills only the listed evidence gaps.",
            schema_name="retrieval_rewrite",
            context={
                "original_query": original_query,
                "missing_aspects": missing_aspects,
            },
            system_prompt=(
                "Return exactly one JSON object with query and purpose. Preserve every animal, entity "
                "ID, number, time expression, and negated statement from the original query. Do not add "
                "a diagnosis or any tool, collection, top_k, provider, or call control."
            ),
        )


def _body(raw: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw).difference(fields | _MODEL_METADATA_FIELDS):
        raise ValueError("model response contains unsupported fields")
    return {key: raw[key] for key in fields if key in raw}


def _model_failure_reason(raw: dict[str, Any]) -> str | None:
    if not isinstance(raw, dict):
        return "schema_validation_failed"
    if raw.get("status") == "error" or raw.get("fallback_required") is True:
        return str(raw.get("error_code") or raw.get("reason") or "model_requested_fallback")
    return None


def _added_diagnoses(original: str, candidate: str) -> list[str]:
    original_folded = original.casefold()
    candidate_folded = candidate.casefold()
    return [
        f"added_diagnosis:{term}"
        for term in _DIAGNOSIS_TERMS
        if term.casefold() in candidate_folded and term.casefold() not in original_folded
    ]


def _query_key(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result


__all__ = [
    "DecompositionOutcome",
    "QueryDecomposer",
    "QueryRewriteGuard",
    "RewriteOutcome",
]
