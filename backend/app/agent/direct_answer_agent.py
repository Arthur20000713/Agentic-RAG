from __future__ import annotations

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
    "资料依据和引用来源类问题；非畜牧领域的问题我会明确说明不在服务范围内。"
)
OUT_OF_SCOPE_DRAFT = "当前问题超出畜牧业辅助问答范围。你可以继续询问养殖管理、饲喂、疾病初步问诊或资料检索相关问题。"
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

        if FeatureFlagService(self.settings).primary_llm_enabled:
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
                },
                system_prompt=(
                    "Return exactly one JSON object for a livestock assistant draft answer. "
                    "Do not include markdown fences. Do not claim citations or diagnosis."
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
            if isinstance(value, str) and value.strip():
                payload["answer_draft"] = value.strip()
                break
    return payload


def _direct_answer_prompt(state: MultiAgentState) -> str:
    if state.intent == "assistant_intro":
        task = "Briefly introduce yourself and what livestock questions you can help with."
    elif state.intent == "measurement_analysis":
        task = "Explain that body-measurement analysis needs structured measurement data through the measurement API."
    else:
        task = "Politely explain the request is outside the livestock assistant scope and invite a livestock-related question."
    return f"{task}\nUser message: {(state.normalized_query or state.user_query).strip()}"
