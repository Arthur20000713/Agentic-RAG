from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.response import ApiResponse
from backend.app.services.runtime_doctor import RuntimeDoctor


API_PREFIX = "/api"
HEALTH_ENDPOINT = "/api/health"
READY_ENDPOINT = "/api/ready"

router = APIRouter(prefix=API_PREFIX, tags=["health"])


@router.get(HEALTH_ENDPOINT.removeprefix(API_PREFIX))
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    return ApiResponse.ok(
        {
            "status": "ok",
            "app": settings.app.name,
            "environment": settings.app.environment,
        }
    ).model_dump()


@router.get(READY_ENDPOINT.removeprefix(API_PREFIX))
async def ready(request: Request) -> dict:
    doctor = RuntimeDoctor(request.app.state.settings)
    return ApiResponse.ok(doctor.check()).model_dump()
