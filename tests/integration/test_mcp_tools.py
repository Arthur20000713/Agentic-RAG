from __future__ import annotations

import asyncio

from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.mcp_server.tools import (
    TOOL_SCHEMAS,
    body_measurement_analyzer,
    disease_risk_evaluator,
    get_source_detail,
    livestock_rag_search,
)


def test_tool_schemas_include_v1_tools() -> None:
    assert set(TOOL_SCHEMAS) == {
        "livestock_rag_search",
        "get_source_detail",
        "disease_risk_evaluator",
        "body_measurement_analyzer",
    }
    assert TOOL_SCHEMAS["livestock_rag_search"]["input_schema"]["required"] == ["query"]
    assert "doc_id" in TOOL_SCHEMAS["get_source_detail"]["input_schema"]["required"]


def test_livestock_rag_search_returns_citations_from_rag_client() -> None:
    result = asyncio.run(
        livestock_rag_search(
            FakeRagServerClient(),
            query="犊牛腹泻怎么办",
            top_k=1,
            domain="disease",
            species="cattle",
        )
    )

    assert result.status == "success"
    assert result.data["query"] == "犊牛腹泻怎么办"
    assert len(result.data["hits"]) == 1
    assert result.data["citations"][0]["title"] == "犊牛腹泻防治技术手册"


def test_livestock_rag_search_error_does_not_fabricate_hits() -> None:
    result = asyncio.run(livestock_rag_search(FakeRagServerClient(), query="失败"))

    assert result.status == "error"
    assert result.data["hits"] == []
    assert result.error is not None
    assert result.error.error_code == "RAG_INTERNAL_ERROR"


def test_get_source_detail_returns_summary() -> None:
    result = asyncio.run(get_source_detail(FakeRagServerClient(), doc_id="doc_001"))

    assert result.status == "success"
    assert result.data["doc_id"] == "doc_001"
    assert "犊牛腹泻" in result.data["summary"]


def test_disease_risk_evaluator_tool_is_rule_based() -> None:
    result = disease_risk_evaluator(
        species="cattle",
        symptoms=["diarrhea", "depression"],
        temperature_c=40.1,
        duration_days=2,
        group_outbreak=False,
    )

    assert result.status == "success"
    assert result.data["risk_level"] == "high"
    assert result.data["need_vet"] is True


def test_body_measurement_analyzer_tool_returns_evidence() -> None:
    result = body_measurement_analyzer(
        animal_id="yak_032",
        current={"chest_girth_cm": 158.4},
        history=[{"measure_date": "2026-04-01", "chest_girth_cm": 157.0}],
        confidence=0.82,
    )

    assert result.status == "success"
    assert "chest_girth_cm" in result.data["abnormal_items"]
    assert result.data["evidence"]
