from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.measurement import BodyMeasurementValues


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    user_id: str | None = None
    animal_id: str | None = None
    stream: bool = False

    @field_validator("query")
    @classmethod
    def validate_query_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class MeasurementAnalyzeRequest(BaseModel):
    animal_id: str
    age_month: int | None = Field(default=None, ge=0)
    current: BodyMeasurementValues
    confidence: float | None = Field(default=None, ge=0, le=1)
    use_demo_history: bool = False
