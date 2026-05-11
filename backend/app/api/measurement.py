from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.response import ApiResponse
from backend.app.db.repositories import MeasurementRepository
from backend.app.schemas.api import MeasurementAnalyzeRequest
from backend.app.schemas.measurement import MeasurementInput
from backend.app.services.measurement_service import MeasurementService


router = APIRouter(prefix="/api/measurement", tags=["measurement"])


@router.post("/analyze")
async def analyze_measurement(payload: MeasurementAnalyzeRequest, request: Request) -> dict:
    measurement = MeasurementInput(
        animal_id=payload.animal_id,
        age_month=payload.age_month,
        current=payload.current,
        confidence=payload.confidence,
        use_demo_history=payload.use_demo_history,
    )
    result = MeasurementService(MeasurementRepository(request.app.state.db_conn)).analyze(measurement)
    return ApiResponse.ok(result.model_dump()).model_dump()

