from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.response import ApiResponse
from backend.app.services.rag_status_service import RagStatusService


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/status")
async def get_rag_status(request: Request) -> dict:
    service = RagStatusService(request.app.state.settings)
    return ApiResponse.ok(service.get_rag_status()).model_dump()
