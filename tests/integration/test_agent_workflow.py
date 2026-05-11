from __future__ import annotations

import asyncio

from backend.app.agent.workflow import run_general_qa
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_general_qa_workflow_uses_fake_rag_and_citations() -> None:
    state = asyncio.run(
        run_general_qa(
            "犊牛腹泻的常见原因是什么？",
            rag_client=FakeRagServerClient(),
            session_id="s_general",
        )
    )

    assert state.intent == "general_qa"
    assert state.final_answer is not None
    assert "参考依据" in state.final_answer
    assert state.retrieved_contexts
    assert "livestock_rag_search" in state.tool_results

