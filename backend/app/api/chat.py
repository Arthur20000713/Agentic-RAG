from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.response import ApiResponse
from backend.app.schemas.api import ChatRequest
from backend.app.services.chat_service import ChatService, state_to_chat_data


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> dict:
    service = ChatService(request.app.state.rag_client)
    state = await service.ask(payload)
    return ApiResponse.ok(state_to_chat_data(state, settings=request.app.state.settings)).model_dump()
