from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.measurement import BodyMeasurementValues


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    user_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    animal_id: str | None = None
    stream: bool = False

    @field_validator("query", mode="before")
    @classmethod
    def validate_query_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class MeasurementAnalyzeRequest(BaseModel):
    animal_id: str
    age_month: int | None = Field(default=None, ge=0)
    current: BodyMeasurementValues
    confidence: float | None = Field(default=None, ge=0, le=1)
    use_demo_history: bool = False
