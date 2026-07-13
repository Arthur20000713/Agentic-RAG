from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, Request

from backend.app.agent.state import MultiAgentState
from backend.app.core.errors import ErrorCode
from backend.app.core.response import ApiResponse, new_request_id
from backend.app.db.repositories import ConversationRepository, QaLogRepository
from backend.app.schemas.agent import AgentState
from backend.app.schemas.api import ChatRequest
from backend.app.services.chat_service import ChatService, state_to_chat_data
from backend.app.services.session_context_service import SessionContextService


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> dict:
    started_at = time.perf_counter()
    request_id = new_request_id()
    if not payload.session_id:
        payload = payload.model_copy(update={"session_id": f"s_{uuid4().hex}"})
    owner_id = payload.user_id or "anonymous"
    conversations = ConversationRepository(request.app.state.db_conn)
    if conversations.get(payload.session_id) is not None and conversations.get(payload.session_id, owner_id) is None:
        return ApiResponse.fail(
            ErrorCode.FORBIDDEN,
            "conversation belongs to another client",
            request_id=request_id,
        ).model_dump()
    qa_logs = QaLogRepository(request.app.state.db_conn)
    history = qa_logs.recent(payload.session_id) if payload.session_id else []
    service = ChatService(
        request.app.state.rag_client,
        settings=request.app.state.settings,
        session_context_service=SessionContextService(request.app.state.db_conn),
        conversation_history=history,
    )
    state = await service.ask(payload, request_id=request_id)
    _record_chat_trace(request, state, request_id)
    chat_data = state_to_chat_data(state, settings=request.app.state.settings)
    try:
        if not conversations.record_turn(
            state.session_id,
            owner_id,
            payload.query,
            commit=False,
        ):
            request.app.state.db_conn.rollback()
            return ApiResponse.fail(
                ErrorCode.FORBIDDEN,
                "conversation belongs to another client",
                request_id=request_id,
            ).model_dump()
        qa_logs.add(
            session_id=state.session_id,
            user_query=payload.query,
            intent=state.intent,
            final_answer=state.final_answer or "",
            tools_used=list(state.tool_results),
            retrieved_chunks=[context.model_dump() for context in state.retrieved_contexts],
            risk_level=state.risk_level,
            latency_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
            response_data=chat_data,
            commit=False,
        )
        request.app.state.db_conn.commit()
    except Exception:
        request.app.state.db_conn.rollback()
        raise
    return ApiResponse.ok(chat_data, request_id=request_id).model_dump()


def _record_chat_trace(request: Request, state: AgentState | MultiAgentState, request_id: str) -> None:
    trace = state.agent_trace if isinstance(state, MultiAgentState) else _v2_trace(state)
    request.app.state.trace_service.record_agent_trace(
        session_id=state.session_id,
        request_id=request_id,
        trace=trace,
        status="failed" if state.errors else "success",
    )


def _v2_trace(state: AgentState) -> list[dict]:
    trace = [{"node": "v2_workflow", "status": "failed" if state.errors else "success"}]
    for tool_name in state.tool_results:
        trace.append({"node": tool_name, "status": "success"})
    return trace
