from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.query_constraints import extract_query_constraints
from backend.app.agent.retrieval_query_strategy import (
    QueryDecomposer,
    QueryRewriteGuard,
)
from backend.app.core.config import Settings


class ScriptedPrimaryLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[Any] = []

    async def generate_json(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return self.payload


def _settings(*, enabled: bool) -> Settings:
    return Settings(
        primary_llm={
            "enabled": enabled,
            "provider": "mock",
            "model": "retrieval-test",
            "base_url": "mock",
        }
    )


def test_decomposer_accepts_bounded_model_queries_and_controls_ids() -> None:
    original = "犊牛 A-17 腹泻2天但没有发热，需要补液和隔离依据"
    client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "queries": [
                {
                    "text": "犊牛 A-17 腹泻2天但没有发热的补液依据",
                    "purpose": "补液",
                },
                {
                    "text": "犊牛 A-17 腹泻2天但没有发热的隔离依据",
                    "purpose": "隔离",
                },
            ],
            "fallback_required": False,
        }
    )

    outcome = asyncio.run(
        QueryDecomposer(
            settings=_settings(enabled=True),
            primary_llm_client=client,
        ).decompose(original)
    )

    assert outcome.source == "model"
    assert outcome.fallback_used is False
    assert [query.query_id for query in outcome.queries] == ["q_primary_1", "q_primary_2"]
    assert all(query.origin == "decomposed" for query in outcome.queries)
    assert client.requests[0].schema_name == "retrieval_decomposition"
    assert client.requests[0].context == {"original_query": original}


def test_decomposer_uses_original_query_when_model_is_disabled() -> None:
    original = "calf C-2 feeding management for 3 days"

    outcome = asyncio.run(
        QueryDecomposer(settings=_settings(enabled=False)).decompose(original)
    )

    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "primary_llm_disabled"
    assert len(outcome.queries) == 1
    assert outcome.queries[0].origin == "original"
    assert outcome.queries[0].text == original


def test_decomposer_rejects_semantic_drift_and_unsupported_control_fields() -> None:
    original = "犊牛 A-17 腹泻2天但没有发热"
    drift_client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "queries": [{"text": "羔羊腹泻治疗", "purpose": "治疗"}],
            "fallback_required": False,
        }
    )
    control_client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "queries": [{"text": original, "purpose": "检索"}],
            "collection": "model-controlled",
            "fallback_required": False,
        }
    )

    drift = asyncio.run(
        QueryDecomposer(
            settings=_settings(enabled=True), primary_llm_client=drift_client
        ).decompose(original)
    )
    controlled = asyncio.run(
        QueryDecomposer(
            settings=_settings(enabled=True), primary_llm_client=control_client
        ).decompose(original)
    )

    assert drift.fallback_reason == "semantic_constraint_violation"
    assert drift.queries[0].text == original
    assert controlled.fallback_reason == "schema_validation_failed"
    assert controlled.queries[0].text == original


def test_decomposer_rejects_more_than_three_model_queries() -> None:
    original = "calf feeding, housing, hydration, and monitoring"
    client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "queries": [
                {"text": f"calf {aspect}", "purpose": aspect}
                for aspect in ("feeding", "housing", "hydration", "monitoring")
            ],
            "fallback_required": False,
        }
    )

    outcome = asyncio.run(
        QueryDecomposer(
            settings=_settings(enabled=True), primary_llm_client=client
        ).decompose(original)
    )

    assert outcome.fallback_reason == "schema_validation_failed"
    assert [query.text for query in outcome.queries] == [original]


def test_rewrite_guard_accepts_one_safe_secondary_query() -> None:
    original = "犊牛 A-17 腹泻2天但没有发热"
    client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "query": f"{original} 的补液量证据",
            "purpose": "补足补液量证据",
            "fallback_required": False,
        }
    )

    outcome = asyncio.run(
        QueryRewriteGuard(
            settings=_settings(enabled=True), primary_llm_client=client
        ).rewrite(
            original_query=original,
            constraints=extract_query_constraints(original),
            missing_aspects=["补液量"],
            previous_queries=[("q_primary_1", original)],
        )
    )

    assert outcome.query is not None
    assert outcome.query.query_id == "q_secondary"
    assert outcome.query.origin == "secondary"
    assert outcome.query.parent_query_ids == ["q_primary_1"]
    assert outcome.rejection_reasons == []


def test_rewrite_guard_rejects_constraint_drift_and_new_diagnosis() -> None:
    original = "犊牛 A-17 咳嗽2天但没有发热"
    constraint_client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "query": "羔羊肺炎治疗",
            "purpose": "治疗",
            "fallback_required": False,
        }
    )
    diagnosis_client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "query": "犊牛 A-17 肺炎治疗2天但没有发热",
            "purpose": "治疗",
            "fallback_required": False,
        }
    )

    constraint = asyncio.run(
        QueryRewriteGuard(
            settings=_settings(enabled=True), primary_llm_client=constraint_client
        ).rewrite(
            original_query=original,
            constraints=extract_query_constraints(original),
            missing_aspects=["治疗"],
            previous_queries=[("q_primary_1", original)],
        )
    )
    diagnosis = asyncio.run(
        QueryRewriteGuard(
            settings=_settings(enabled=True), primary_llm_client=diagnosis_client
        ).rewrite(
            original_query=original,
            constraints=extract_query_constraints(original),
            missing_aspects=["治疗"],
            previous_queries=[("q_primary_1", original)],
        )
    )

    assert constraint.query is None
    assert "semantic_constraint_violation" in constraint.rejection_reasons
    assert diagnosis.query is None
    assert diagnosis.rejection_reasons == ["added_diagnosis:肺炎"]


def test_rewrite_guard_uses_bounded_deterministic_fallback() -> None:
    original = "Ewe E-9 has not coughed for 48 hours"

    outcome = asyncio.run(
        QueryRewriteGuard(settings=_settings(enabled=False)).rewrite(
            original_query=original,
            constraints=extract_query_constraints(original),
            missing_aspects=["hydration", "housing", "monitoring", "ignored"],
            previous_queries=[("q_primary_1", original)],
        )
    )

    assert outcome.query is not None
    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "primary_llm_disabled"
    assert outcome.query.text == f"{original} hydration; housing; monitoring"


def test_rewrite_guard_rejects_duplicate_historical_query() -> None:
    original = "calf feeding management"
    client = ScriptedPrimaryLLM(
        {
            "status": "success",
            "query": original,
            "purpose": "repeat",
            "fallback_required": False,
        }
    )

    outcome = asyncio.run(
        QueryRewriteGuard(
            settings=_settings(enabled=True), primary_llm_client=client
        ).rewrite(
            original_query=original,
            constraints=extract_query_constraints(original),
            missing_aspects=["feeding"],
            previous_queries=[("q_primary_1", original)],
        )
    )

    assert outcome.query is None
    assert outcome.rejection_reasons == ["duplicate_query"]
