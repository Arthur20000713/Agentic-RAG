from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.agent.graph import run_measurement_graph
from backend.app.core.response import ApiResponse
from backend.app.db.repositories import MeasurementRepository, MemoryRepository
from backend.app.schemas.api import MeasurementAnalyzeRequest
from backend.app.schemas.measurement import MeasurementAnalysisResult, MeasurementInput
from backend.app.services.feature_flag_service import FeatureFlagService
from backend.app.services.measurement_service import MeasurementService
from backend.app.services.memory_service import MemoryService


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
    prepared_measurement = MeasurementService(
        MeasurementRepository(request.app.state.db_conn)
    ).prepare_input(measurement)
    settings = request.app.state.settings
    memory_service: MemoryService | None = None
    if FeatureFlagService(settings).memory_write_enabled:
        memory_service = MemoryService(
            event_writer=MemoryRepository(request.app.state.db_conn).append_event
        )
    state = await run_measurement_graph(
        prepared_measurement,
        memory_service=memory_service,
        settings=settings,
    )
    result = MeasurementAnalysisResult.model_validate(state.measurement_report)
    return ApiResponse.ok(result.model_dump()).model_dump()
