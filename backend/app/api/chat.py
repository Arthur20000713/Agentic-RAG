from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.agent.state import MultiAgentState
from backend.app.core.response import ApiResponse, new_request_id
from backend.app.schemas.agent import AgentState
from backend.app.schemas.api import ChatRequest
from backend.app.services.chat_service import ChatService, state_to_chat_data


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> dict:
    request_id = new_request_id()
    service = ChatService(request.app.state.rag_client, settings=request.app.state.settings)
    state = await service.ask(payload, request_id=request_id)
    _record_chat_trace(request, state, request_id)
    return ApiResponse.ok(state_to_chat_data(state, settings=request.app.state.settings), request_id=request_id).model_dump()


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
