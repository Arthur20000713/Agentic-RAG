from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.response import ApiResponse


router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("/{request_id}")
async def get_trace_bundle(request: Request, request_id: str) -> dict:
    agent_trace = request.app.state.trace_service.list_agent_traces(request_id)
    return ApiResponse.ok(
        {
            "request_id": request_id,
            "agent_trace": agent_trace,
            "tool_trace": [],
            "rag_trace": [],
            "safety_result": None,
            "verifier_result": None,
        }
    ).model_dump()
