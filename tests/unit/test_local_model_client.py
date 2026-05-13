from __future__ import annotations

import asyncio

from backend.app.model.base import BaseModelClient
from backend.app.model.local_client import LocalModelClient


def test_local_model_client_implements_base_model_client() -> None:
    client = LocalModelClient()

    assert isinstance(client, BaseModelClient)


def test_local_model_client_returns_deterministic_query_normalization_json() -> None:
    client = LocalModelClient()

    first = asyncio.run(client.generate_json("  Calf feeding after weaning  ", schema_name="query_normalization"))
    second = asyncio.run(client.generate_json("  Calf feeding after weaning  ", schema_name="query_normalization"))

    assert first == second
    assert first == {
        "status": "success",
        "schema_name": "query_normalization",
        "normalized_query": "Calf feeding after weaning",
        "language": "en",
        "fallback_required": False,
    }


def test_local_model_client_detects_chinese_query_language() -> None:
    client = LocalModelClient()

    result = asyncio.run(client.generate_json("犊牛断奶后怎么饲喂？", schema_name="query_normalization"))

    assert result["language"] == "zh"
    assert result["normalized_query"] == "犊牛断奶后怎么饲喂？"


def test_local_model_client_refuses_final_answer_schema() -> None:
    client = LocalModelClient()

    result = asyncio.run(client.generate_json("high risk answer", schema_name="final_answer"))

    assert result["status"] == "unsupported"
    assert result["fallback_required"] is True
    assert "structured JSON" in result["reason"]


def test_local_model_client_returns_fixed_json_for_generic_structured_task() -> None:
    client = LocalModelClient()

    result = asyncio.run(
        client.generate_json(
            "extract slots",
            schema_name="slot_extraction",
            context={"intent": "disease_consultation", "session_id": "s1"},
        )
    )

    assert result == {
        "status": "success",
        "schema_name": "slot_extraction",
        "fields": {},
        "confidence": 0.0,
        "fallback_required": False,
        "provider": "mock",
        "context_keys": ["intent", "session_id"],
    }
