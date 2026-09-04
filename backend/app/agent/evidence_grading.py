from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from backend.app.schemas.rag_server import RagSearchHit, RagSearchResult
from backend.app.schemas.retrieval import (
    EvidenceConflict,
    EvidenceGrade,
    RetrievalQuery,
)

_RELEVANCE_THRESHOLD = 0.55
_COVERAGE_THRESHOLD = 1.0
_SOURCE_QUALITY_THRESHOLD = 1.0
_MAX_OBSERVED_HITS = 64


@dataclass(frozen=True)
class AggregatedEvidence:
    hits: list[RagSearchHit]
    hit_keys: list[str]
    query_hit_keys: dict[str, list[str]]
    query_statuses: dict[str, str]

    @property
    def hit_by_key(self) -> dict[str, RagSearchHit]:
        return dict(zip(self.hit_keys, self.hits, strict=True))


class EvidenceAggregator:
    def aggregate(
        self,
        results: list[tuple[str, RagSearchResult]],
    ) -> AggregatedEvidence:
        hits: list[RagSearchHit] = []
        hit_keys: list[str] = []
        key_indexes: dict[str, int] = {}
        query_hit_keys: dict[str, list[str]] = {}
        query_statuses: dict[str, str] = {}

        for query_id, result in results:
            query_statuses[query_id] = result.status
            query_keys = query_hit_keys.setdefault(query_id, [])
            if result.status == "error":
                continue
            for hit in result.hits:
                key = evidence_hit_key(hit)
                existing_index = key_indexes.get(key)
                if existing_index is None and len(hits) >= _MAX_OBSERVED_HITS:
                    continue
                if key not in query_keys:
                    query_keys.append(key)
                if existing_index is None:
                    key_indexes[key] = len(hits)
                    hit_keys.append(key)
                    hits.append(hit.model_copy(deep=True))
                    continue
                existing = hits[existing_index]
                if hit.score_type == existing.score_type and hit.score > existing.score:
                    hits[existing_index] = hit.model_copy(deep=True)

        return AggregatedEvidence(
            hits=hits,
            hit_keys=hit_keys,
            query_hit_keys=query_hit_keys,
            query_statuses=query_statuses,
        )


class EvidenceGrader:
    def __init__(self, *, relevance_threshold: float = _RELEVANCE_THRESHOLD) -> None:
        if not 0.0 <= relevance_threshold <= 1.0:
            raise ValueError("relevance threshold must be between 0 and 1")
        self.relevance_threshold = relevance_threshold

    def grade(
        self,
        *,
        round: int,
        queries: list[RetrievalQuery],
        evidence: AggregatedEvidence,
    ) -> EvidenceGrade:
        if round not in {1, 2}:
            raise ValueError("evidence grade round must be 1 or 2")
        if not queries:
            raise ValueError("at least one retrieval query is required")

        relevance = self._relevance(evidence.hits)
        covered_ids = {
            query.query_id
            for query in queries
            if evidence.query_hit_keys.get(query.query_id)
        }
        coverage = len(covered_ids) / len(queries)
        source_quality = self._source_quality(evidence.hits)
        missing_aspects = [
            query.purpose for query in queries if query.query_id not in covered_ids
        ][:3]
        conflicts = self._conflicts(evidence)
        reason_codes: list[str] = []

        if not evidence.hits:
            reason_codes.append("no_evidence")
        if relevance < self.relevance_threshold:
            reason_codes.append("relevance_below_threshold")
        if coverage < _COVERAGE_THRESHOLD:
            reason_codes.append("coverage_below_threshold")
        if source_quality < _SOURCE_QUALITY_THRESHOLD:
            reason_codes.append("source_quality_below_threshold")
        if conflicts:
            reason_codes.append("evidence_conflict")
        if "low_confidence" in evidence.query_statuses.values():
            reason_codes.append("upstream_low_confidence")
        if reason_codes and not missing_aspects:
            missing_aspects = [query.purpose for query in queries][:3]

        decision = "sufficient" if not reason_codes else ("refine" if round == 1 else "no_answer")
        return EvidenceGrade(
            round=round,
            relevance=relevance,
            coverage=coverage,
            source_quality=source_quality,
            missing_aspects=missing_aspects,
            conflicts=conflicts,
            reason_codes=reason_codes,
            decision=decision,
        )

    def _relevance(self, hits: list[RagSearchHit]) -> float:
        scores = [
            min(1.0, max(0.0, hit.score))
            for hit in hits
            if hit.score_type != "unknown"
        ]
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    def _source_quality(self, hits: list[RagSearchHit]) -> float:
        if not hits:
            return 0.0
        traceable = sum(has_traceable_source(hit) for hit in hits)
        return round(traceable / len(hits), 4)

    def _conflicts(self, evidence: AggregatedEvidence) -> list[EvidenceConflict]:
        claims: dict[str, dict[str, str]] = {}
        for key, hit in zip(evidence.hit_keys, evidence.hits, strict=True):
            topic = str(hit.metadata.get("claim_topic") or "").strip()
            value = str(hit.metadata.get("claim_value") or "").strip()
            if topic and value:
                claims.setdefault(topic, {}).setdefault(value.casefold(), key)

        conflicts: list[EvidenceConflict] = []
        for topic, value_refs in claims.items():
            refs = list(value_refs.values())
            if len(refs) > 1:
                conflicts.append(
                    EvidenceConflict(
                        topic=topic[:200],
                        left_ref=refs[0],
                        right_ref=refs[1],
                    )
                )
            if len(conflicts) == 3:
                break
        return conflicts


def evidence_hit_key(hit: RagSearchHit) -> str:
    if hit.source_uri:
        raw = f"{hit.source_uri}#{hit.chunk_id}"
    else:
        raw = f"chunk://{hit.collection or 'default'}/{hit.document_id or 'unknown'}/{hit.chunk_id}"
    if len(raw) <= 256:
        return raw
    return f"evidence://{sha256(raw.encode('utf-8')).hexdigest()}"


def has_traceable_source(hit: RagSearchHit) -> bool:
    source = (hit.source_uri or "").casefold()
    return bool(
        source
        and hit.chunk_id
        and "unknown-doc-" not in source
        and "unknown-chunk-" not in source
    )


__all__ = [
    "AggregatedEvidence",
    "EvidenceAggregator",
    "EvidenceGrader",
    "evidence_hit_key",
    "has_traceable_source",
]
