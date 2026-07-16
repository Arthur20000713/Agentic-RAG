from __future__ import annotations

import asyncio

from backend.app.agent.graph import run_chat_graph, run_disease_graph
from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.services.session_context_service import SessionContextService


class FakeDiseaseLLM:
    async def generate_json(self, request) -> dict:
        if request.schema_name == "disease_case_understanding":
            text = request.prompt
            if "换成羊" in text:
                return {
                    "status": "success",
                    "schema_name": "disease_case_understanding",
                    "case_summary": "Sheep has cough.",
                    "species": "sheep",
                    "observed_signs": ["cough"],
                }
            return {
                "status": "success",
                "schema_name": "disease_case_understanding",
                "case_summary": "Cattle has diarrhea and reduced appetite.",
                "species": "cattle",
                "observed_signs": ["diarrhea", "reduced appetite"],
                "context_factors": ["normal temperature"],
            }
        return {
            "status": "success",
            "schema_name": "grounded_rag_answer",
            "answer_draft": "Monitor the calf using the retrieved guidance [1].",
            "evidence_sufficient": True,
            "fallback_required": False,
        }


def _session_service() -> SessionContextService:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    return SessionContextService(conn)


def test_session_follow_up_flow_merges_dynamic_disease_context() -> None:
    service = _session_service()
    settings = Settings(
        v3={"enabled": True},
        primary_llm={"enabled": True, "provider": "mock", "model": "mock", "base_url": "mock", "api_key_env": "X"},
        disease_llm={"enabled": True, "shadow_mode": False, "require_rag_evidence": True},
    )
    llm = FakeDiseaseLLM()

    first = asyncio.run(
        run_disease_graph(
            "牛拉稀了怎么办？",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_follow",
            settings=settings,
            primary_llm_client=llm,
        )
    )
    second = asyncio.run(
        run_disease_graph(
            "已经两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_follow",
            settings=settings,
            primary_llm_client=llm,
        )
    )

    context = service.get_context("s_follow")

    assert first.disease_assessment is not None
    assert first.disease_assessment["status"] == "rag_ready"
    assert "livestock_rag_search" in first.tool_results
    assert second.normalized_query is not None
    assert "Cattle has diarrhea" in second.normalized_query
    assert "diarrhea" in second.normalized_query
    assert second.disease_assessment is not None
    assert second.disease_assessment["status"] == "rag_ready"
    assert "livestock_rag_search" in second.tool_results
    assert second.final_answer is not None
    assert "初步风险等级" not in second.final_answer
    assert context is not None
    assert context.pending_slots == []


def test_unified_chat_graph_keeps_bare_symptom_follow_up_on_disease_branch() -> None:
    service = _session_service()
    settings = Settings(
        v3={"enabled": True},
        primary_llm={"enabled": True, "provider": "mock", "model": "mock", "base_url": "mock"},
        disease_llm={"enabled": True, "shadow_mode": False},
    )
    llm = FakeDiseaseLLM()

    first = asyncio.run(
        run_chat_graph(
            "A calf has diarrhea and reduced appetite.",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_bare_symptom_follow_up",
            settings=settings,
            primary_llm_client=llm,
        )
    )
    second = asyncio.run(
        run_chat_graph(
            "Fever is still present.",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_bare_symptom_follow_up",
            settings=settings,
            primary_llm_client=llm,
        )
    )

    assert first.intent == "disease_consultation"
    assert second.intent == "disease_consultation"
    assert second.normalized_query is not None
    assert "Cattle has diarrhea" in second.normalized_query
    assert "livestock_rag_search" in second.tool_results


def test_session_follow_up_flow_reset_clears_conflicted_context() -> None:
    service = _session_service()
    settings = Settings(
        v3={"enabled": True},
        primary_llm={"enabled": True, "provider": "mock", "model": "mock", "base_url": "mock", "api_key_env": "X"},
        disease_llm={"enabled": True, "shadow_mode": False, "require_rag_evidence": True},
    )
    llm = FakeDiseaseLLM()
    asyncio.run(
        run_disease_graph(
            "牛拉稀了怎么办？",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_reset",
            settings=settings,
            primary_llm_client=llm,
        )
    )

    reset = asyncio.run(
        run_disease_graph(
            "换成羊咳嗽一天，体温40.1度，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_context_service=service,
            session_id="s_reset",
            settings=settings,
            primary_llm_client=llm,
        )
    )

    context = service.get_context("s_reset")

    assert reset.normalized_query == reset.user_query.strip()
    assert "腹泻" not in reset.normalized_query
    assert context is not None
    assert context.last_species == "sheep"
    assert "diarrhea" not in context.last_symptoms
