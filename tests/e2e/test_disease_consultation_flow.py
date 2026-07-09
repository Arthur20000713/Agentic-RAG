from __future__ import annotations

import asyncio

from backend.app.agent.workflow import run_disease_consultation
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_disease_consultation_uses_rag_without_fixed_follow_up() -> None:
    state = asyncio.run(
        run_disease_consultation(
            "牛拉稀了怎么办？",
            rag_client=FakeRagServerClient(),
            session_id="s_follow",
        )
    )

    assert state.intent == "disease_consultation"
    assert state.need_follow_up is False
    assert state.follow_up_questions == []
    assert "livestock_rag_search" in state.tool_results
    assert "slot_extractor" not in state.tool_results


def test_disease_consultation_rag_branch_without_rule_risk() -> None:
    state = asyncio.run(
        run_disease_consultation(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_id="s_risk",
        )
    )

    assert state.need_follow_up is False
    assert state.risk_level is None
    assert "disease_risk_evaluator" not in state.tool_results
    assert "livestock_rag_search" in state.tool_results
    assert state.final_answer is not None
    assert "参考依据" in state.final_answer


def test_disease_consultation_final_safety_blocks_unsafe_draft() -> None:
    state = asyncio.run(
        run_disease_consultation(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_id="s_safe",
            unsafe_draft_for_test="确诊为肠炎，使用药物 5 mg/kg。",
        )
    )

    assert state.final_answer is not None
    assert "5 mg/kg" not in state.final_answer
    assert "不能提供具体药物剂量" in state.final_answer
