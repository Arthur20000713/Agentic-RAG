from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.direct_answer_agent import DirectAnswerAgent
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMRequest


class FakePrimaryLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[PrimaryLLMRequest] = []

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.payload


def test_direct_answer_agent_uses_primary_llm_for_draft_only() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "direct_answer_draft",
            "answer_draft": "你好，我是畜牧业智能助手，可以结合知识库和工具回答养殖相关问题。",
            "fallback_required": False,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="hello", intent="assistant_intro")

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "你好，我是畜牧业智能助手，可以结合知识库和工具回答养殖相关问题。"
    assert state.final_answer is None
    assert llm.requests[0].schema_name == "direct_answer_draft"
    assert llm.requests[0].context["intent"] == "assistant_intro"
    assert state.tool_results["direct_answer_planner"]["status"] == "success"
    assert state.agent_trace[-1]["node"] == "direct_answer_planner"


def test_direct_answer_agent_accepts_llm_schema_name_alias_when_answer_draft_is_valid() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "assistant_intro",
            "answer_draft": "Hello, I can help with livestock health, feeding, and management questions.",
            "fallback_required": False,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="hello", intent="assistant_intro")

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "Hello, I can help with livestock health, feeding, and management questions."
    assert state.tool_results["direct_answer_planner"]["fallback_used"] is False


def test_direct_answer_agent_accepts_response_field_as_answer_draft_alias() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "direct_answer_draft",
            "response": "Hello, I can help with livestock health, nutrition, and management.",
            "fallback_required": False,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="hello", intent="assistant_intro")

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "Hello, I can help with livestock health, nutrition, and management."
    assert state.tool_results["direct_answer_planner"]["fallback_used"] is False


def test_direct_answer_agent_accepts_message_field_as_answer_draft_alias() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "direct_answer_draft",
            "message": "Hello, I can help with livestock health and management.",
            "fallback_required": False,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="hello", intent="assistant_intro")

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "Hello, I can help with livestock health and management."
    assert state.tool_results["direct_answer_planner"]["fallback_used"] is False


def test_direct_answer_agent_accepts_content_field_as_answer_draft_alias() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "direct_answer_draft",
            "content": "Hello, I can help with livestock questions.",
            "fallback_required": False,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="hello", intent="assistant_intro")

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "Hello, I can help with livestock questions."
    assert state.tool_results["direct_answer_planner"]["fallback_used"] is False


def test_direct_answer_agent_accepts_answer_without_explicit_status() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM({"answer": "A short, friendly joke."})
    state = MultiAgentState(session_id="s1", user_query="Tell me a joke", intent="out_of_scope")

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "A short, friendly joke."


def test_direct_answer_agent_supplies_recent_session_history_to_llm() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "answer_draft": "You just told me your name is Xiaolin.",
            "fallback_required": False,
        }
    )
    state = MultiAgentState(session_id="s1", user_query="What did I just tell you?", intent="out_of_scope")
    state.session_context["conversation_history"] = [
        {"user": "My name is Xiaolin.", "assistant": "Nice to meet you, Xiaolin."}
    ]

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert llm.requests[0].context["conversation_history"][0]["user"] == "My name is Xiaolin."
    assert "My name is Xiaolin" in llm.requests[0].prompt


def test_direct_answer_agent_accepts_nested_response_and_ok_status() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM({"status": "ok", "response": {"text": "Your name is Xiaogang."}})
    state = MultiAgentState(session_id="s1", user_query="What is my name?", intent="out_of_scope")

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "Your name is Xiaogang."


def test_direct_answer_agent_recalls_explicit_name_from_session_history_without_llm_variance() -> None:
    settings = Settings(
        primary_llm={"enabled": True, "provider": "deepseek", "model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com"},
    )
    llm = FakePrimaryLLM({"status": "error", "fallback_required": True})
    state = MultiAgentState(session_id="s1", user_query="我叫什么名字？", intent="out_of_scope")
    state.session_context["conversation_history"] = [
        {"user": "我的名字是小兰，请记住。", "assistant": "好的，小兰，我记住了。"},
        {"user": "我叫什么名字？", "assistant": "抱歉，我暂时无法确认。"},
    ]

    asyncio.run(DirectAnswerAgent(settings=settings, primary_llm_client=llm).run(state))

    assert state.draft_answer == "你的名字是小兰。"
    assert llm.requests == []
    assert state.tool_results["direct_answer_planner"]["fallback_used"] is False
