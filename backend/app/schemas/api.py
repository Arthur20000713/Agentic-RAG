from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.measurement import BodyMeasurementValues


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: str | None = None
    user_id: str | None = None
    animal_id: str | None = None
    stream: bool = False


class MeasurementAnalyzeRequest(BaseModel):
    animal_id: str
    age_month: int | None = Field(default=None, ge=0)
    current: BodyMeasurementValues
    confidence: float | None = Field(default=None, ge=0, le=1)
    use_demo_history: bool = False

