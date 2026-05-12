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
        "sources": _state_sources(state),
        "tools_used": list(state.tool_results),
        "need_follow_up": state.need_follow_up,
        "follow_up_questions": state.follow_up_questions,
        "errors": [error.model_dump() for error in state.errors],
    }


def _state_sources(state: AgentState) -> list[dict]:
    rag_result = state.tool_results.get("livestock_rag_search")
    if isinstance(rag_result, dict) and rag_result.get("status") == "success":
        hits = list(rag_result.get("hits") or [])
        sources: list[dict] = []
        seen: set[str] = set()
        for citation in rag_result.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            hit = _matching_hit(citation, hits)
            source_uri = citation.get("source_uri") or (hit or {}).get("source_uri")
            key = source_uri or "|".join(
                str(citation.get(field) or "")
                for field in ("source_id", "chunk_id", "title", "page")
            )
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "source_uri": source_uri,
                    "title": citation.get("title") or (hit or {}).get("document_title"),
                    "page": citation.get("page"),
                    "section_title": citation.get("section_title"),
                    "chunk_id": citation.get("chunk_id") or (hit or {}).get("chunk_id"),
                }
            )
        return sources

    return [
        {
            "source_uri": None,
            "title": item.title,
            "page": item.page,
            "section_title": item.section_title,
            "chunk_id": item.chunk_id,
        }
        for item in state.retrieved_contexts
    ]


def _matching_hit(citation: dict, hits: list[dict]) -> dict | None:
    chunk_id = citation.get("chunk_id")
    if chunk_id:
        for hit in hits:
            if hit.get("chunk_id") == chunk_id:
                return hit

    source_id = citation.get("source_id")
    title = citation.get("title")
    for hit in hits:
        if source_id is not None and str(hit.get("document_id")) == str(source_id):
            return hit
        if title and hit.get("document_title") == title:
            return hit
    return None
