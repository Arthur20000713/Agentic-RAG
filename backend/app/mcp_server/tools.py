from __future__ import annotations

from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.mcp import ToolResult


TOOL_SCHEMAS = {
    "livestock_rag_search": {
        "name": "livestock_rag_search",
        "description": "Search livestock knowledge through the RAG-SERVER adapter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "domain": {"type": "string"},
                "species": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
                "collection": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    "get_source_detail": {
        "name": "get_source_detail",
        "description": "Fetch source summary details from RAG-SERVER.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "collection": {"type": "string"},
            },
            "required": ["doc_id"],
        },
    },
    "disease_risk_evaluator": {
        "name": "disease_risk_evaluator",
        "description": "Evaluate livestock disease risk by deterministic rules.",
        "input_schema": {
            "type": "object",
            "properties": {
                "species": {"type": "string"},
                "age_stage": {"type": "string"},
                "symptoms": {"type": "array", "items": {"type": "string"}},
                "temperature_c": {"type": "number"},
                "duration_days": {"type": "number"},
                "group_outbreak": {"type": "boolean"},
            },
            "required": ["species", "symptoms"],
        },
    },
    "body_measurement_analyzer": {
        "name": "body_measurement_analyzer",
        "description": "Analyze yak body measurement values with rule-based evidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "animal_id": {"type": "string"},
                "age_month": {"type": "integer", "minimum": 0},
                "current": {"type": "object"},
                "history": {"type": "array", "items": {"type": "object"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["animal_id", "current"],
        },
    },
}


async def livestock_rag_search(
    client: RagServerClient,
    *,
    query: str,
    top_k: int = 4,
    collection: str | None = None,
    domain: str | None = None,
    species: str | None = None,
) -> ToolResult:
    result = await client.query(
        query,
        top_k=top_k,
        collection=collection,
        domain=domain,
        species=species,
    )
    data = {
        "query": result.query,
        "status": result.status,
        "hits": [hit.model_dump() for hit in result.hits],
        "citations": [citation.model_dump() for citation in result.citations],
        "answer_text": result.answer_text,
    }
    if result.status == "error":
        return ToolResult.failure(
            "livestock_rag_search",
            result.error_code or "RAG_INTERNAL_ERROR",
            result.error_message or "rag server query failed",
            data=data,
        )
    return ToolResult.success("livestock_rag_search", data)


async def get_source_detail(
    client: RagServerClient,
    *,
    doc_id: str,
    collection: str | None = None,
) -> ToolResult:
    summary = await client.get_document_summary(doc_id, collection=collection)
    return ToolResult.success("get_source_detail", summary.model_dump())

