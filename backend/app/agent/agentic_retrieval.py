from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from backend.app.agent.evidence_grading import (
    AggregatedEvidence,
    EvidenceAggregator,
    EvidenceGrader,
    has_traceable_source,
)
from backend.app.agent.query_constraints import extract_query_constraints
from backend.app.agent.retrieval_query_strategy import (
    QueryDecomposer,
    QueryRewriteGuard,
)
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.rag_server import RagCitation, RagSearchHit, RagSearchResult
from backend.app.schemas.retrieval import (
    MAX_FINAL_HITS,
    MAX_RETRIEVAL_QUERY_CALLS,
    AgenticRetrievalState,
    EvidenceGrade,
    RetrievalAttempt,
    RetrievalQuery,
    RetrievalQuerySource,
)


@dataclass(frozen=True)
class AgenticRetrievalOutcome:
    result: RagSearchResult
    state: AgenticRetrievalState
    infrastructure_failed: bool


class AgenticRetrievalOrchestrator:
    def __init__(
        self,
        rag_client: RagServerClient,
        *,
        settings: Settings | None = None,
        primary_llm_client: Any | None = None,
        decomposer: Any | None = None,
        rewrite_guard: Any | None = None,
        aggregator: EvidenceAggregator | None = None,
        grader: EvidenceGrader | None = None,
        top_k: int = 4,
        collection: str | None = None,
    ) -> None:
        app_settings = settings or Settings()
        self.rag_client = rag_client
        self.decomposer = decomposer or QueryDecomposer(
            settings=app_settings,
            primary_llm_client=primary_llm_client,
        )
        self.rewrite_guard = rewrite_guard or QueryRewriteGuard(
            settings=app_settings,
            primary_llm_client=primary_llm_client,
        )
        self.aggregator = aggregator or EvidenceAggregator()
        self.grader = grader or EvidenceGrader()
        self.top_k = max(1, min(int(top_k), 20))
        self.collection = collection

    async def run(
        self,
        *,
        original_query: str,
        query_source: RetrievalQuerySource,
        request_id: str | None,
        operation_prefix: str,
    ) -> AgenticRetrievalOutcome:
        constraints = extract_query_constraints(original_query)
        decomposition = await self.decomposer.decompose(original_query)
        primary_queries = decomposition.queries
        if not 1 <= len(primary_queries) <= 3:
            raise ValueError("decomposer must return between one and three primary queries")

        attempts: list[RetrievalAttempt] = []
        results: list[tuple[str, RagSearchResult]] = []
        for query in primary_queries:
            result, attempt = await self._search(
                query=query,
                round=1,
                request_id=request_id,
                operation_prefix=operation_prefix,
            )
            results.append((query.query_id, result))
            attempts.append(attempt)

        evidence = self.aggregator.aggregate(results)
        first_grade = self.grader.grade(
            round=1,
            queries=primary_queries,
            evidence=evidence,
        )
        grades = [first_grade]
        if self._all_failed(attempts) and not evidence.hits:
            return self._error_outcome(
                original_query=original_query,
                query_source=query_source,
                constraints=constraints,
                primary_queries=primary_queries,
                attempts=attempts,
                grades=grades,
                evidence=evidence,
            )
        if first_grade.decision == "sufficient":
            return self._sufficient_outcome(
                original_query=original_query,
                query_source=query_source,
                constraints=constraints,
                primary_queries=primary_queries,
                secondary_query=None,
                attempts=attempts,
                grades=grades,
                evidence=evidence,
                results=results,
            )

        gap_queries = [
            query for query in primary_queries if query.purpose in first_grade.missing_aspects
        ] or primary_queries
        rewrite = await self.rewrite_guard.rewrite(
            original_query=original_query,
            constraints=constraints,
            missing_aspects=first_grade.missing_aspects,
            previous_queries=[(query.query_id, query.text) for query in gap_queries],
        )
        if rewrite.query is None:
            return self._insufficient_outcome(
                original_query=original_query,
                query_source=query_source,
                constraints=constraints,
                primary_queries=primary_queries,
                secondary_query=None,
                attempts=attempts,
                grades=grades,
                evidence=evidence,
                results=results,
                termination_code="REWRITE_REJECTED",
            )
        secondary_query = rewrite.query
        if len(attempts) >= MAX_RETRIEVAL_QUERY_CALLS:
            raise RuntimeError("semantic retrieval call budget exhausted before secondary query")

        secondary_result, secondary_attempt = await self._search(
            query=secondary_query,
            round=2,
            request_id=request_id,
            operation_prefix=operation_prefix,
        )
        attempts.append(secondary_attempt)
        results.append((secondary_query.query_id, secondary_result))
        evidence = self._propagate_secondary_coverage(
            self.aggregator.aggregate(results),
            secondary_query,
        )
        second_grade = self.grader.grade(
            round=2,
            queries=primary_queries,
            evidence=evidence,
        )
        grades.append(second_grade)
        if second_grade.decision == "sufficient":
            return self._sufficient_outcome(
                original_query=original_query,
                query_source=query_source,
                constraints=constraints,
                primary_queries=primary_queries,
                secondary_query=secondary_query,
                attempts=attempts,
                grades=grades,
                evidence=evidence,
                results=results,
            )
        return self._insufficient_outcome(
            original_query=original_query,
            query_source=query_source,
            constraints=constraints,
            primary_queries=primary_queries,
            secondary_query=secondary_query,
            attempts=attempts,
            grades=grades,
            evidence=evidence,
            results=results,
            termination_code="EVIDENCE_INSUFFICIENT_AFTER_SECONDARY",
        )

    async def _search(
        self,
        *,
        query: RetrievalQuery,
        round: int,
        request_id: str | None,
        operation_prefix: str,
    ) -> tuple[RagSearchResult, RetrievalAttempt]:
        operation_key = _operation_key(operation_prefix, round, query.query_id)
        try:
            result = await self.rag_client.query(
                query.text,
                top_k=self.top_k,
                collection=self.collection,
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001 - transport exceptions become structured attempts
            result = RagSearchResult(
                query=query.text,
                status="error",
                error_code="RAG_QUERY_EXCEPTION",
                error_message=str(exc) or exc.__class__.__name__,
            )
        if result.status == "error":
            attempt = RetrievalAttempt(
                round=round,
                query_id=query.query_id,
                operation_key=operation_key,
                status="error",
                hit_count=len(result.hits),
                error_code=(result.error_code or "RAG_QUERY_ERROR")[:96],
            )
        else:
            attempt = RetrievalAttempt(
                round=round,
                query_id=query.query_id,
                operation_key=operation_key,
                status=result.status,
                hit_count=len(result.hits),
                result_ref=f"rag_r{round}_{query.query_id}",
            )
        return result, attempt

    def _sufficient_outcome(self, **kwargs: Any) -> AgenticRetrievalOutcome:
        evidence: AggregatedEvidence = kwargs["evidence"]
        selected_hits = evidence.hits[:MAX_FINAL_HITS]
        selected_keys = evidence.hit_keys[: len(selected_hits)]
        result = RagSearchResult(
            query=kwargs["original_query"],
            status="success",
            hits=selected_hits,
            citations=[_citation(hit) for hit in selected_hits if has_traceable_source(hit)],
            mapping_warnings=_mapping_warnings(kwargs["results"]),
        )
        state = self._state(
            **kwargs,
            selected_keys=selected_keys,
            final_status="sufficient",
            termination_code=None,
        )
        return AgenticRetrievalOutcome(result=result, state=state, infrastructure_failed=False)

    def _insufficient_outcome(self, **kwargs: Any) -> AgenticRetrievalOutcome:
        result = RagSearchResult(
            query=kwargs["original_query"],
            status="low_confidence",
            mapping_warnings=_mapping_warnings(kwargs["results"]),
        )
        state = self._state(
            **kwargs,
            selected_keys=[],
            final_status="insufficient",
        )
        return AgenticRetrievalOutcome(result=result, state=state, infrastructure_failed=False)

    def _error_outcome(self, **kwargs: Any) -> AgenticRetrievalOutcome:
        result = RagSearchResult(
            query=kwargs["original_query"],
            status="error",
            error_code="RAG_ALL_QUERIES_FAILED",
            error_message="all retrieval queries failed without usable evidence",
        )
        state = self._state(
            **kwargs,
            secondary_query=None,
            selected_keys=[],
            final_status="error",
            termination_code="RAG_ALL_QUERIES_FAILED",
        )
        return AgenticRetrievalOutcome(result=result, state=state, infrastructure_failed=True)

    def _state(
        self,
        *,
        original_query: str,
        query_source: RetrievalQuerySource,
        constraints: Any,
        primary_queries: list[RetrievalQuery],
        secondary_query: RetrievalQuery | None,
        attempts: list[RetrievalAttempt],
        grades: list[EvidenceGrade],
        evidence: AggregatedEvidence,
        selected_keys: list[str],
        final_status: str,
        termination_code: str | None,
        **_: Any,
    ) -> AgenticRetrievalState:
        return AgenticRetrievalState(
            original_query=original_query,
            query_source=query_source,
            constraints=constraints,
            primary_queries=primary_queries,
            secondary_query=secondary_query,
            attempts=attempts,
            grades=grades,
            rag_call_count=len(attempts),
            secondary_retrieval_count=int(secondary_query is not None),
            observed_hit_keys=evidence.hit_keys,
            selected_hit_keys=selected_keys,
            final_status=final_status,
            termination_code=termination_code,
        )

    def _propagate_secondary_coverage(
        self,
        evidence: AggregatedEvidence,
        secondary_query: RetrievalQuery,
    ) -> AggregatedEvidence:
        query_hit_keys = {
            query_id: list(keys) for query_id, keys in evidence.query_hit_keys.items()
        }
        query_statuses = dict(evidence.query_statuses)
        secondary_keys = query_hit_keys.get(secondary_query.query_id, [])
        for parent_id in secondary_query.parent_query_ids:
            parent_keys = query_hit_keys.setdefault(parent_id, [])
            parent_keys.extend(key for key in secondary_keys if key not in parent_keys)
            if secondary_keys and query_statuses.get(secondary_query.query_id) == "success":
                query_statuses[parent_id] = "success"
        return AggregatedEvidence(
            hits=evidence.hits,
            hit_keys=evidence.hit_keys,
            query_hit_keys=query_hit_keys,
            query_statuses=query_statuses,
        )

    def _all_failed(self, attempts: list[RetrievalAttempt]) -> bool:
        return bool(attempts) and all(attempt.status == "error" for attempt in attempts)


def _operation_key(prefix: str, round: int, query_id: str) -> str:
    raw = f"{prefix}:r{round}:{query_id}"
    if len(raw) <= 256:
        return raw
    digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{raw[:239]}:{digest}"


def _citation(hit: RagSearchHit) -> RagCitation:
    return RagCitation(
        source_id=str(hit.document_id) if hit.document_id is not None else None,
        source_uri=hit.source_uri,
        title=hit.document_title,
        page=hit.page,
        section_title=hit.section_title,
        chunk_id=hit.chunk_id,
    )

def _mapping_warnings(results: list[tuple[str, RagSearchResult]]) -> list[str]:
    warnings: list[str] = []
    for _, result in results:
        warnings.extend(item for item in result.mapping_warnings if item not in warnings)
    return warnings


__all__ = ["AgenticRetrievalOrchestrator", "AgenticRetrievalOutcome"]
