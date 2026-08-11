from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.graph import run_general_qa_graph
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.model.base import BaseModelClient
from backend.app.services.chat_service import state_to_chat_data


class InvalidQueryNormalizerClient(BaseModelClient):
    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"status": "success", "normalized_query": "", "language": "invalid"}


def test_local_query_normalizer_schema_failure_falls_back_and_is_observable() -> None:
    settings = Settings(
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["query_normalization"],
        },
        local_model={"enabled": True},
    )

    state = asyncio.run(
        run_general_qa_graph(
            "  How should cattle feeding be managed?  ",
            rag_client=FakeRagServerClient(),
            session_id="s_v5_fallback",
            settings=settings,
            query_normalizer_client=InvalidQueryNormalizerClient(),
        )
    )

    assert state.final_answer
    assert state.normalized_query == "How should cattle feeding be managed?"
    router_payload = state.tool_results["query_normalizer_router"]
    assert router_payload["fallback_used"] is True
    assert router_payload["fallback_reason"] == "schema_validation_failed"
    assert state.tool_results["model_fallbacks"] == [
        {
            "component": "query_normalizer",
            "selected_model": "local_small",
            "fallback_reason": "schema_validation_failed",
            "route_mode": "takeover",
        }
    ]

    data = state_to_chat_data(state, settings=settings)
    assert data["agent_runtime_debug"]["model_fallbacks"] == state.tool_results["model_fallbacks"]
