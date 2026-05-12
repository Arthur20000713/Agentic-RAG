from __future__ import annotations

import asyncio

from backend.app.agent.graph import run_disease_graph
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.services.session_context_service import SessionContextService


def _session_service() -> SessionContextService:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    return SessionContextService(conn)


def test_session_follow_up_flow_merges_pending_disease_slots() -> None:
    service = _session_service()

    first = asyncio.run(
        run_disease_graph(
            "牛拉稀了怎么办？",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_follow",
        )
    )
    second = asyncio.run(
        run_disease_graph(
            "已经两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_follow",
        )
    )

    context = service.get_context("s_follow")

    assert first.disease_assessment is not None
    assert first.disease_assessment["status"] == "follow_up"
    assert "livestock_rag_search" not in first.tool_results
    assert second.normalized_query is not None
    assert "牛" in second.normalized_query
    assert "腹泻" in second.normalized_query
    assert second.disease_assessment is not None
    assert second.disease_assessment["risk_level"] == "high"
    assert "livestock_rag_search" in second.tool_results
    assert second.final_answer is not None
    assert "初步风险等级：high" in second.final_answer
    assert context is not None
    assert context.pending_slots == []


def test_session_follow_up_flow_reset_clears_conflicted_context() -> None:
    service = _session_service()
    asyncio.run(
        run_disease_graph(
            "牛拉稀了怎么办？",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_reset",
        )
    )

    reset = asyncio.run(
        run_disease_graph(
            "换成羊咳嗽一天，体温40.1度，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_reset",
        )
    )

    context = service.get_context("s_reset")

    assert reset.normalized_query == reset.user_query.strip()
    assert "腹泻" not in reset.normalized_query
    assert reset.extracted_slots["species"] == "sheep"
    assert "cough" in reset.extracted_slots["symptoms"]
    assert context is not None
    assert context.last_species == "sheep"
    assert "diarrhea" not in context.last_symptoms
