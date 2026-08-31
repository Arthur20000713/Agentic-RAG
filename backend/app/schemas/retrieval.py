from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PRIMARY_SUBQUERIES = 3
MAX_SECONDARY_RETRIEVALS = 1
MAX_RETRIEVAL_QUERY_CALLS = 4
MAX_FINAL_HITS = 12
MAX_RETRIEVAL_QUERY_LENGTH = 500

RetrievalQueryOrigin = Literal["original", "decomposed", "secondary"]
RetrievalQuerySource = Literal["normalized_query", "rag_query"]
RetrievalAttemptStatus = Literal["success", "empty", "low_confidence", "error"]
EvidenceDecision = Literal["sufficient", "refine", "no_answer"]
AgenticRetrievalStatus = Literal[
    "pending",
    "sufficient",
    "insufficient",
    "blocked",
    "error",
]


class QueryConstraintSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[str] = Field(default_factory=list, max_length=16)
    numeric_or_temporal_terms: list[str] = Field(default_factory=list, max_length=16)
    negated_spans: list[str] = Field(default_factory=list, max_length=8)


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1, max_length=64, pattern=r"^q_[a-z0-9_]+$")
    text: str = Field(min_length=1, max_length=MAX_RETRIEVAL_QUERY_LENGTH)
    origin: RetrievalQueryOrigin
    purpose: str = Field(min_length=1, max_length=200)
    parent_query_ids: list[str] = Field(default_factory=list, max_length=MAX_PRIMARY_SUBQUERIES)

    @model_validator(mode="after")
    def validate_parent_contract(self) -> RetrievalQuery:
        if len(set(self.parent_query_ids)) != len(self.parent_query_ids):
            raise ValueError("parent query IDs must be unique")
        if self.query_id in self.parent_query_ids:
            raise ValueError("query cannot be its own parent")
        if self.origin == "secondary" and not self.parent_query_ids:
            raise ValueError("secondary query requires at least one parent query")
        if self.origin != "secondary" and self.parent_query_ids:
            raise ValueError("only secondary queries may have parent query IDs")
        return self


class RetrievalAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = Field(ge=1, le=2)
    query_id: str = Field(min_length=1, max_length=64, pattern=r"^q_[a-z0-9_]+$")
    operation_key: str = Field(min_length=1, max_length=256)
    status: RetrievalAttemptStatus
    hit_count: int = Field(default=0, ge=0, le=100)
    result_ref: str | None = Field(default=None, min_length=1, max_length=128)
    error_code: str | None = Field(default=None, min_length=1, max_length=96)

    @model_validator(mode="after")
    def validate_attempt_contract(self) -> RetrievalAttempt:
        if self.status == "error" and self.error_code is None:
            raise ValueError("error retrieval attempts require error_code")
        if self.status != "error" and self.error_code is not None:
            raise ValueError("only error retrieval attempts may contain error_code")
        if self.status != "error" and self.result_ref is None:
            raise ValueError("non-error retrieval attempts require result_ref")
        return self


class EvidenceConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=200)
    left_ref: str = Field(min_length=1, max_length=256)
    right_ref: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_distinct_refs(self) -> EvidenceConflict:
        if self.left_ref == self.right_ref:
            raise ValueError("conflict refs must be distinct")
        return self


class EvidenceGrade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = Field(ge=1, le=2)
    relevance: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    source_quality: float = Field(ge=0, le=1)
    missing_aspects: list[str] = Field(default_factory=list, max_length=3)
    conflicts: list[EvidenceConflict] = Field(default_factory=list, max_length=3)
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    decision: EvidenceDecision

    @model_validator(mode="after")
    def validate_decision_contract(self) -> EvidenceGrade:
        if self.decision == "sufficient" and (self.missing_aspects or self.conflicts):
            raise ValueError("sufficient evidence cannot have missing aspects or conflicts")
        return self


class AgenticRetrievalState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_query: str = Field(min_length=1, max_length=MAX_RETRIEVAL_QUERY_LENGTH)
    query_source: RetrievalQuerySource
    constraints: QueryConstraintSnapshot
    decomposition_source: str = Field(default="unknown", min_length=1, max_length=32)
    decomposition_fallback_reason: str | None = Field(default=None, max_length=96)
    rewrite_source: str | None = Field(default=None, max_length=32)
    rewrite_fallback_reason: str | None = Field(default=None, max_length=96)
    rewrite_rejection_reasons: list[str] = Field(default_factory=list, max_length=8)
    primary_queries: list[RetrievalQuery] = Field(
        min_length=1,
        max_length=MAX_PRIMARY_SUBQUERIES,
    )
    secondary_query: RetrievalQuery | None = None
    attempts: list[RetrievalAttempt] = Field(
        default_factory=list,
        max_length=MAX_RETRIEVAL_QUERY_CALLS,
    )
    grades: list[EvidenceGrade] = Field(default_factory=list, max_length=2)
    rag_call_count: int = Field(default=0, ge=0, le=MAX_RETRIEVAL_QUERY_CALLS)
    secondary_retrieval_count: int = Field(default=0, ge=0, le=MAX_SECONDARY_RETRIEVALS)
    observed_hit_keys: list[str] = Field(default_factory=list, max_length=64)
    selected_hit_keys: list[str] = Field(default_factory=list, max_length=MAX_FINAL_HITS)
    final_status: AgenticRetrievalStatus = "pending"
    termination_code: str | None = Field(default=None, min_length=1, max_length=96)

    @model_validator(mode="after")
    def validate_retrieval_contract(self) -> AgenticRetrievalState:
        primary_ids = [query.query_id for query in self.primary_queries]
        if len(set(primary_ids)) != len(primary_ids):
            raise ValueError("primary query IDs must be unique")
        if any(query.origin == "secondary" for query in self.primary_queries):
            raise ValueError("primary queries cannot have secondary origin")

        if self.secondary_query is not None:
            if self.secondary_query.origin != "secondary":
                raise ValueError("secondary query must have secondary origin")
            if not set(self.secondary_query.parent_query_ids) <= set(primary_ids):
                raise ValueError("secondary query references an unknown parent query")
            if self.secondary_retrieval_count != 1:
                raise ValueError("secondary query requires secondary retrieval count 1")
        elif self.secondary_retrieval_count:
            raise ValueError("secondary retrieval count requires a secondary query")

        known_query_ids = set(primary_ids)
        if self.secondary_query is not None:
            known_query_ids.add(self.secondary_query.query_id)
        if any(attempt.query_id not in known_query_ids for attempt in self.attempts):
            raise ValueError("retrieval attempt references an unknown query")
        if any(
            (attempt.query_id == getattr(self.secondary_query, "query_id", None))
            != (attempt.round == 2)
            for attempt in self.attempts
        ):
            raise ValueError("retrieval attempt round must match query origin")
        if len({attempt.operation_key for attempt in self.attempts}) != len(self.attempts):
            raise ValueError("retrieval operation keys must be unique")
        if self.rag_call_count != len(self.attempts):
            raise ValueError("rag_call_count must match retrieval attempts")

        observed = set(self.observed_hit_keys)
        if not set(self.selected_hit_keys) <= observed:
            raise ValueError("selected hit keys must exist in observed hits")
        for grade in self.grades:
            conflict_refs = {
                ref
                for conflict in grade.conflicts
                for ref in (conflict.left_ref, conflict.right_ref)
            }
            if not conflict_refs <= observed:
                raise ValueError("conflict refs must exist in observed hits")

        grade_rounds = [grade.round for grade in self.grades]
        if grade_rounds != sorted(set(grade_rounds)):
            raise ValueError("evidence grade rounds must be unique and ordered")
        if self.final_status == "sufficient":
            if not self.grades or self.grades[-1].decision != "sufficient":
                raise ValueError("sufficient retrieval requires a sufficient final grade")
            if not self.selected_hit_keys:
                raise ValueError("sufficient retrieval requires selected hits")
        if self.final_status in {"blocked", "error"} and self.termination_code is None:
            raise ValueError("blocked or error retrieval requires termination_code")
        return self


__all__ = [
    "MAX_FINAL_HITS",
    "MAX_PRIMARY_SUBQUERIES",
    "MAX_RETRIEVAL_QUERY_CALLS",
    "MAX_RETRIEVAL_QUERY_LENGTH",
    "MAX_SECONDARY_RETRIEVALS",
    "AgenticRetrievalState",
    "AgenticRetrievalStatus",
    "EvidenceConflict",
    "EvidenceDecision",
    "EvidenceGrade",
    "QueryConstraintSnapshot",
    "RetrievalAttempt",
    "RetrievalAttemptStatus",
    "RetrievalQuery",
    "RetrievalQueryOrigin",
    "RetrievalQuerySource",
]
