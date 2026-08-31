from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.agent.query_constraints import (
    extract_query_constraints,
    semantic_constraint_violations,
)
from backend.app.schemas.retrieval import (
    AgenticRetrievalState,
    EvidenceConflict,
    EvidenceGrade,
    RetrievalAttempt,
    RetrievalQuery,
)


def _query(query_id: str, text: str, *, origin: str = "decomposed") -> RetrievalQuery:
    return RetrievalQuery(
        query_id=query_id,
        text=text,
        origin=origin,
        purpose="retrieve one bounded aspect",
    )


def _grade(*, decision: str = "sufficient") -> EvidenceGrade:
    return EvidenceGrade(
        round=1,
        relevance=0.9,
        coverage=1.0,
        source_quality=1.0,
        decision=decision,
    )


def test_agentic_retrieval_state_accepts_a_bounded_sufficient_result() -> None:
    state = AgenticRetrievalState(
        original_query="calf feeding and water management",
        query_source="normalized_query",
        constraints=extract_query_constraints("calf feeding and water management"),
        primary_queries=[
            _query("q_feed", "calf feeding management"),
            _query("q_water", "calf water management"),
        ],
        attempts=[
            RetrievalAttempt(
                round=1,
                query_id="q_feed",
                operation_key="request:plan:retrieve:r1:q_feed",
                status="success",
                hit_count=2,
                result_ref="rag_round_1_q_feed",
            ),
            RetrievalAttempt(
                round=1,
                query_id="q_water",
                operation_key="request:plan:retrieve:r1:q_water",
                status="success",
                hit_count=1,
                result_ref="rag_round_1_q_water",
            ),
        ],
        grades=[_grade()],
        rag_call_count=2,
        observed_hit_keys=["rag://default/feed#c1", "rag://default/water#c2"],
        selected_hit_keys=["rag://default/feed#c1", "rag://default/water#c2"],
        final_status="sufficient",
    )

    restored = AgenticRetrievalState.model_validate_json(state.model_dump_json())

    assert restored == state
    assert restored.rag_call_count == 2


def test_retrieval_schema_rejects_query_and_call_budget_overflow() -> None:
    with pytest.raises(ValidationError, match="at most 3 items"):
        AgenticRetrievalState(
            original_query="complex query",
            query_source="normalized_query",
            constraints=extract_query_constraints("complex query"),
            primary_queries=[_query(f"q_{index}", f"aspect {index}") for index in range(4)],
        )

    with pytest.raises(ValidationError, match="less than or equal to 4"):
        AgenticRetrievalState(
            original_query="query",
            query_source="normalized_query",
            constraints=extract_query_constraints("query"),
            primary_queries=[_query("q_original", "query", origin="original")],
            rag_call_count=5,
        )


def test_retrieval_schema_rejects_invalid_secondary_and_conflict_refs() -> None:
    with pytest.raises(ValidationError, match="secondary query must have secondary origin"):
        AgenticRetrievalState(
            original_query="query",
            query_source="normalized_query",
            constraints=extract_query_constraints("query"),
            primary_queries=[_query("q_original", "query", origin="original")],
            secondary_query=_query("q_secondary", "query guidance"),
            secondary_retrieval_count=1,
        )

    with pytest.raises(ValidationError, match="unknown parent query"):
        AgenticRetrievalState(
            original_query="query",
            query_source="normalized_query",
            constraints=extract_query_constraints("query"),
            primary_queries=[_query("q_original", "query", origin="original")],
            secondary_query=RetrievalQuery(
                query_id="q_secondary",
                text="query guidance",
                origin="secondary",
                purpose="fill an evidence gap",
                parent_query_ids=["q_missing"],
            ),
            secondary_retrieval_count=1,
        )

    with pytest.raises(ValidationError, match="conflict refs must exist"):
        AgenticRetrievalState(
            original_query="query",
            query_source="normalized_query",
            constraints=extract_query_constraints("query"),
            primary_queries=[_query("q_original", "query", origin="original")],
            grades=[
                EvidenceGrade(
                    round=1,
                    relevance=0.8,
                    coverage=1.0,
                    source_quality=1.0,
                    conflicts=[
                        EvidenceConflict(
                            topic="water allowance",
                            left_ref="rag://default/a#c1",
                            right_ref="rag://default/missing#c9",
                        )
                    ],
                    decision="refine",
                )
            ],
            observed_hit_keys=["rag://default/a#c1"],
        )


def test_retrieval_schema_rejects_attempt_round_mismatch() -> None:
    with pytest.raises(ValidationError, match="round must match query origin"):
        AgenticRetrievalState(
            original_query="query",
            query_source="normalized_query",
            constraints=extract_query_constraints("query"),
            primary_queries=[_query("q_original", "query", origin="original")],
            attempts=[
                RetrievalAttempt(
                    round=2,
                    query_id="q_original",
                    operation_key="request:plan:retrieve:r2:q_original",
                    status="empty",
                    result_ref="rag_round_2_q_original",
                )
            ],
            rag_call_count=1,
        )


@pytest.mark.parametrize(
    ("query", "entities", "numeric_terms", "negated_text"),
    [
        (
            "犊牛 A-17 腹泻2天但没有发热",
            {"犊牛", "A-17"},
            {"2天"},
            "没有发热",
        ),
        (
            "Ewe E-9 has not coughed for 48 hours",
            {"ewe", "E-9"},
            {"48 hours"},
            "not coughed for 48 hours",
        ),
    ],
)
def test_constraint_extractor_captures_entities_time_and_negation(
    query: str,
    entities: set[str],
    numeric_terms: set[str],
    negated_text: str,
) -> None:
    snapshot = extract_query_constraints(query)

    assert entities <= set(snapshot.entities)
    assert numeric_terms <= set(snapshot.numeric_or_temporal_terms)
    assert any(negated_text.casefold() in span.casefold() for span in snapshot.negated_spans)


def test_semantic_guard_accepts_preserved_constraints_and_rejects_drift() -> None:
    original = "犊牛 A-17 腹泻2天但没有发热"
    snapshot = extract_query_constraints(original)

    assert semantic_constraint_violations(
        snapshot,
        ["犊牛 A-17 腹泻2天", "犊牛 A-17 没有发热的护理依据"],
    ) == []

    violations = semantic_constraint_violations(
        snapshot,
        ["羔羊腹泻护理", "发热治疗依据"],
    )

    assert "missing_entity:A-17" in violations
    assert "missing_entity:犊牛" in violations
    assert "missing_numeric_or_temporal:2天" in violations
    assert "missing_negated_span:没有发热" in violations
    assert "added_entity:羔羊" in violations


def test_semantic_guard_rejects_new_negation() -> None:
    snapshot = extract_query_constraints("calf C-2 has coughed for 3 days")

    violations = semantic_constraint_violations(
        snapshot,
        ["calf C-2 has not coughed for 3 days"],
    )

    assert "added_negation:not" in violations
