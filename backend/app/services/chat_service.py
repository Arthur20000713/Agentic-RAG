from __future__ import annotations

from backend.app.agent.router import IntentRouter
from backend.app.agent.workflow import run_disease_consultation, run_general_qa
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.agent import AgentState
from backend.app.schemas.api import ChatRequest


class ChatService:
    def __init__(self, rag_client: RagServerClient) -> None:
        self.rag_client = rag_client
        self.router = IntentRouter()

    async def ask(self, request: ChatRequest) -> AgentState:
        route = self.router.route(request.query)
        if route.intent == "disease_consultation":
            return await run_disease_consultation(
                request.query,
                rag_client=self.rag_client,
                session_id=request.session_id,
            )
        if route.intent == "general_qa":
            return await run_general_qa(
                request.query,
                rag_client=self.rag_client,
                session_id=request.session_id,
            )
        state = AgentState(
            session_id=request.session_id or "s_api",
            user_query=request.query,
            intent=route.intent,
            intent_confidence=route.confidence,
        )
        if route.intent == "measurement_analysis":
            state.final_answer = "请使用 /api/measurement/analyze 提交结构化体尺数据。"
        else:
            state.final_answer = "当前问题超出畜牧业辅助问答范围。"
        return state


def state_to_chat_data(state: AgentState) -> dict:
    return {
        "answer": state.final_answer,
        "intent": state.intent,
        "risk_level": state.risk_level,
        "sources": [
            {
                "title": item.title,
                "page": item.page,
                "chunk_id": item.chunk_id,
            }
            for item in state.retrieved_contexts
        ],
        "tools_used": list(state.tool_results),
        "need_follow_up": state.need_follow_up,
        "follow_up_questions": state.follow_up_questions,
        "errors": [error.model_dump() for error in state.errors],
    }

