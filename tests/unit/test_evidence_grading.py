from __future__ import annotations

from backend.app.agent.evidence_grading import EvidenceAggregator, EvidenceGrader
from backend.app.schemas.rag_server import RagSearchHit, RagSearchResult
from backend.app.schemas.retrieval import RetrievalQuery


def _query(query_id: str, text: str, purpose: str) -> RetrievalQuery:
    return RetrievalQuery(
        query_id=query_id,
        text=text,
        origin="decomposed",
        purpose=purpose,
    )


def _hit(
    chunk_id: str,
    *,
    source_uri: str | None,
    score: float = 0.8,
    score_type: str = "rag_server_score",
    metadata: dict | None = None,
) -> RagSearchHit:
    return RagSearchHit(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        document_title=f"Guide {chunk_id}",
        content=f"Evidence content for {chunk_id}",
        source_uri=source_uri,
        score=score,
        score_type=score_type,
        metadata=metadata or {},
    )


def _result(query: str, *hits: RagSearchHit) -> RagSearchResult:
    return RagSearchResult(query=query, status="success", hits=list(hits))


def test_aggregator_deduplicates_by_source_and_chunk_with_comparable_scores() -> None:
    first = _hit("c1", source_uri="rag://default/doc", score=0.6)
    better = _hit("c1", source_uri="rag://default/doc", score=0.9)
    incomparable = _hit(
        "c2",
        source_uri="rag://default/other",
        score=0.99,
        score_type="mapped_score",
    )
    original_type = _hit(
        "c2",
        source_uri="rag://default/other",
        score=0.4,
        score_type="rag_server_score",
    )

    aggregated = EvidenceAggregator().aggregate(
        [
            ("q_1", _result("first", first, original_type)),
            ("q_2", _result("second", better, incomparable)),
        ]
    )

    assert [hit.chunk_id for hit in aggregated.hits] == ["c1", "c2"]
    assert aggregated.hits[0].score == 0.9
    assert aggregated.hits[1].score == 0.4
    assert aggregated.query_hit_keys["q_1"] == aggregated.query_hit_keys["q_2"]


def test_aggregator_builds_stable_fallback_key_without_source_uri() -> None:
    hit = _hit("c_missing", source_uri=None)

    first = EvidenceAggregator().aggregate([("q_1", _result("query", hit))])
    second = EvidenceAggregator().aggregate([("q_1", _result("query", hit))])

    assert first.hit_keys == second.hit_keys
    assert first.hit_keys[0].startswith("chunk://")


def test_aggregator_caps_checkpoint_observed_hits() -> None:
    hits = [
        _hit(f"c{index}", source_uri=f"rag://kb/doc_{index}")
        for index in range(65)
    ]

    evidence = EvidenceAggregator().aggregate([("q_1", _result("query", *hits))])

    assert len(evidence.hits) == 64
    assert len(evidence.hit_keys) == 64
    assert len(evidence.query_hit_keys["q_1"]) == 64


def test_grader_accepts_complete_relevant_and_traceable_evidence() -> None:
    queries = [
        _query("q_feed", "calf feeding", "feeding"),
        _query("q_water", "calf water", "water"),
    ]
    evidence = EvidenceAggregator().aggregate(
        [
            (
                "q_feed",
                _result("calf feeding", _hit("feed", source_uri="rag://kb/feed", score=0.9)),
            ),
            (
                "q_water",
                _result("calf water", _hit("water", source_uri="rag://kb/water", score=0.8)),
            ),
        ]
    )

    grade = EvidenceGrader().grade(round=1, queries=queries, evidence=evidence)

    assert grade.decision == "sufficient"
    assert grade.coverage == 1.0
    assert grade.source_quality == 1.0
    assert grade.missing_aspects == []
    assert grade.conflicts == []


def test_grader_refines_once_then_returns_no_answer_for_missing_coverage() -> None:
    queries = [
        _query("q_feed", "calf feeding", "feeding"),
        _query("q_water", "calf water", "water"),
    ]
    evidence = EvidenceAggregator().aggregate(
        [
            (
                "q_feed",
                _result("calf feeding", _hit("feed", source_uri="rag://kb/feed")),
            ),
            ("q_water", RagSearchResult(query="calf water", status="empty")),
        ]
    )

    first = EvidenceGrader().grade(round=1, queries=queries, evidence=evidence)
    second = EvidenceGrader().grade(round=2, queries=queries, evidence=evidence)

    assert first.decision == "refine"
    assert first.missing_aspects == ["water"]
    assert "coverage_below_threshold" in first.reason_codes
    assert second.decision == "no_answer"


def test_grader_rejects_unknown_source_quality_after_second_round() -> None:
    queries = [_query("q_feed", "calf feeding", "feeding")]
    evidence = EvidenceAggregator().aggregate(
        [
            (
                "q_feed",
                _result(
                    "calf feeding",
                    _hit(
                        "unknown-chunk-123",
                        source_uri="rag://default/unknown-doc-123/unknown-chunk-123",
                    ),
                ),
            )
        ]
    )

    first = EvidenceGrader().grade(round=1, queries=queries, evidence=evidence)
    second = EvidenceGrader().grade(round=2, queries=queries, evidence=evidence)

    assert first.decision == "refine"
    assert first.source_quality == 0.0
    assert "source_quality_below_threshold" in first.reason_codes
    assert second.decision == "no_answer"


def test_grader_requires_every_selected_source_to_be_traceable() -> None:
    queries = [_query("q_feed", "calf feeding", "feeding")]
    evidence = EvidenceAggregator().aggregate(
        [
            (
                "q_feed",
                _result(
                    "calf feeding",
                    _hit("known", source_uri="rag://kb/known"),
                    _hit(
                        "unknown-chunk-2",
                        source_uri="rag://kb/unknown-doc-2/unknown-chunk-2",
                    ),
                ),
            )
        ]
    )

    grade = EvidenceGrader().grade(round=1, queries=queries, evidence=evidence)

    assert grade.source_quality == 0.5
    assert grade.decision == "refine"


def test_grader_surfaces_traceable_conflicts_and_never_marks_them_sufficient() -> None:
    queries = [_query("q_water", "calf water allowance", "water allowance")]
    left = _hit(
        "left",
        source_uri="rag://kb/left",
        metadata={"claim_topic": "water allowance", "claim_value": "2 litres"},
    )
    right = _hit(
        "right",
        source_uri="rag://kb/right",
        metadata={"claim_topic": "water allowance", "claim_value": "4 litres"},
    )
    evidence = EvidenceAggregator().aggregate(
        [("q_water", _result("calf water allowance", left, right))]
    )

    first = EvidenceGrader().grade(round=1, queries=queries, evidence=evidence)
    second = EvidenceGrader().grade(round=2, queries=queries, evidence=evidence)

    assert first.decision == "refine"
    assert first.reason_codes == ["evidence_conflict"]
    assert first.conflicts[0].left_ref in evidence.hit_keys
    assert first.conflicts[0].right_ref in evidence.hit_keys
    assert second.decision == "no_answer"


def test_grader_treats_empty_evidence_as_a_bounded_refinement() -> None:
    queries = [_query("q_feed", "calf feeding", "feeding")]
    evidence = EvidenceAggregator().aggregate(
        [("q_feed", RagSearchResult(query="calf feeding", status="empty"))]
    )

    grade = EvidenceGrader().grade(round=1, queries=queries, evidence=evidence)

    assert grade.decision == "refine"
    assert grade.relevance == 0.0
    assert grade.missing_aspects == ["feeding"]
    assert "no_evidence" in grade.reason_codes


def test_grader_does_not_upgrade_an_upstream_low_confidence_result() -> None:
    queries = [_query("q_feed", "calf feeding", "feeding")]
    result = _result(
        "calf feeding",
        _hit("feed", source_uri="rag://kb/feed", score=0.95),
    ).model_copy(update={"status": "low_confidence"})
    evidence = EvidenceAggregator().aggregate([("q_feed", result)])

    first = EvidenceGrader().grade(round=1, queries=queries, evidence=evidence)
    second = EvidenceGrader().grade(round=2, queries=queries, evidence=evidence)

    assert first.decision == "refine"
    assert "upstream_low_confidence" in first.reason_codes
    assert second.decision == "no_answer"
