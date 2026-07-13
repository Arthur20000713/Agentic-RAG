from __future__ import annotations

import re
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest
from backend.app.services.feature_flag_service import FeatureFlagService


ASSISTANT_INTRO_DRAFT = (
    "你好，我是 Livestock Agentic RAG 智能助手，主要面向畜牧业知识问答、疾病初步问诊、"
    "体尺分析和资料检索。你可以问我牛、羊、猪等养殖管理、饲喂、断奶、常见症状处理、"
    "资料依据和引用来源类问题，也可以和我进行普通交流。"
)
OUT_OF_SCOPE_DRAFT = "我可以直接和你交流；如果问题涉及畜牧业，我还会结合知识库资料回答。"
MEASUREMENT_CHAT_DRAFT = "体尺分析需要结构化体尺数据。请使用 /api/measurement/analyze 提交动物编号、体高、体长、胸围等数据。"


class DirectAnswerDraftPayload(BaseModel):
    status: Literal["success"]
    schema_name: str = "direct_answer_draft"
    answer_draft: str = Field(min_length=1)
    fallback_required: bool = False
    reason: str | None = None


class DirectAnswerAgent:
    def __init__(self, settings: Settings | None = None, primary_llm_client: Any | None = None) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    async def run(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "direct_answer_planner"
        fallback_answer = fallback_direct_answer(state.intent)
        payload: dict[str, Any] | None = None
        fallback_reason: str | None = None

        contextual_answer = _contextual_history_answer(state)
        if contextual_answer:
            payload = {"answer_draft": contextual_answer}
            state.draft_answer = contextual_answer
        elif FeatureFlagService(self.settings).primary_llm_enabled:
            payload, fallback_reason = await self._generate_with_primary_llm(state)
            if payload is not None:
                state.draft_answer = payload["answer_draft"]

        if not state.draft_answer:
            state.draft_answer = fallback_answer
            fallback_reason = fallback_reason or "primary_llm_disabled"

        state.evidence_status = "empty"
        state.tool_results["direct_answer_planner"] = {
            "status": "success" if payload is not None else "fallback",
            "schema_name": "direct_answer_draft",
            "fallback_used": payload is None,
            "fallback_reason": fallback_reason,
            "intent": state.intent,
        }
        state.agent_trace.append(
            {
                "node": "direct_answer_planner",
                "status": "success" if payload is not None else "fallback",
                "intent": state.intent,
                "fallback_used": payload is None,
                "fallback_reason": fallback_reason,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    async def _generate_with_primary_llm(self, state: MultiAgentState) -> tuple[dict[str, str] | None, str | None]:
        raw = await self.primary_llm_client.generate_json(
            PrimaryLLMRequest(
                prompt=_direct_answer_prompt(state),
                schema_name="direct_answer_draft",
                context={
                    "intent": state.intent,
                    "user_query": state.user_query,
                    "normalized_query": state.normalized_query or state.user_query,
                    "conversation_history": _conversation_history(state),
                },
                system_prompt=(
                    "Return exactly one JSON object for a helpful conversational assistant reply. "
                    "Use the supplied recent conversation history when the current message refers to it. "
                    "Prioritize the current user message and do not claim to remember anything outside that history. "
                    "Do not include markdown fences or claim knowledge-base citations."
                ),
            )
        )
        raw = _normalize_direct_answer_payload(raw)
        try:
            payload = DirectAnswerDraftPayload.model_validate(raw)
        except ValidationError:
            return None, "schema_validation_failed"
        if payload.fallback_required:
            return None, payload.reason or "model_requested_fallback"
        return {"answer_draft": payload.answer_draft}, None


def fallback_direct_answer(intent: str | None) -> str:
    if intent == "assistant_intro":
        return ASSISTANT_INTRO_DRAFT
    if intent == "measurement_analysis":
        return MEASUREMENT_CHAT_DRAFT
    return OUT_OF_SCOPE_DRAFT


def _normalize_direct_answer_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    if not str(payload.get("answer_draft") or "").strip():
        for alias in ("answer_draft", "response", "message", "answer", "draft", "content", "text", "reply", "assistant_response", "introduction"):
            value = payload.get(alias)
            answer_text = _answer_text(value)
            if answer_text:
                payload["answer_draft"] = answer_text
                break
    if str(payload.get("answer_draft") or "").strip() and payload.get("status") in {None, "", "ok", "completed"}:
        payload["status"] = "success"
    return payload


def _answer_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("answer_draft", "response", "message", "answer", "content", "text", "reply"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    if isinstance(value, list):
        for item in value:
            nested = _answer_text(item)
            if nested:
                return nested
    return None


def _direct_answer_prompt(state: MultiAgentState) -> str:
    if state.intent == "assistant_intro":
        task = "Briefly introduce yourself and what livestock questions you can help with."
    elif state.intent == "measurement_analysis":
        task = "Explain that body-measurement analysis needs structured measurement data through the measurement API."
    else:
        task = "Respond naturally and helpfully to the user's ordinary conversation without using RAG citations."
    history = _conversation_history(state)
    history_text = "\n".join(
        f"User: {item.get('user', '')}\nAssistant: {item.get('assistant', '')}"
        for item in history
    )
    history_section = f"\nRecent conversation:\n{history_text}" if history_text else ""
    return f"{task}{history_section}\nCurrent user message: {(state.normalized_query or state.user_query).strip()}"


def _conversation_history(state: MultiAgentState) -> list[dict[str, Any]]:
    value = state.session_context.get("conversation_history")
    if not isinstance(value, list):
        return []
    return [item for item in value[-6:] if isinstance(item, dict)]


def _contextual_history_answer(state: MultiAgentState) -> str | None:
    query = state.user_query.strip()
    lowered = query.lower()
    asks_name = any(
        marker in lowered
        for marker in ("我叫什么", "我的名字是什么", "你记得我的名字", "what is my name", "what's my name", "remember my name")
    )
    if not asks_name:
        return None

    for item in reversed(_conversation_history(state)):
        user_text = str(item.get("user") or "")
        chinese_match = re.search(r"我的名字是\s*([^\s，。！？,!?]{1,20})", user_text)
        if chinese_match is None:
            chinese_match = re.search(r"我叫(?!什么)\s*([^\s，。！？,!?]{1,20})", user_text)
        if chinese_match:
            return f"你的名字是{chinese_match.group(1)}。"
        english_match = re.search(
            r"(?:my name is|call me)\s+([A-Za-z][A-Za-z' -]{0,39})",
            user_text,
            flags=re.IGNORECASE,
        )
        if english_match:
            name = english_match.group(1).strip().rstrip(".,!?")
            return f"Your name is {name}."
    return None
