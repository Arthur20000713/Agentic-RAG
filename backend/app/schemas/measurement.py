from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


class BodyMeasurementValues(BaseModel):
    body_height_cm: float | None = Field(default=None, ge=0)
    body_length_cm: float | None = Field(default=None, ge=0)
    chest_girth_cm: float | None = Field(default=None, ge=0)
    chest_depth_cm: float | None = Field(default=None, ge=0)
    chest_width_cm: float | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_one_measurement(self) -> "BodyMeasurementValues":
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("at least one measurement value is required")
        return self


class MeasurementHistoryItem(BodyMeasurementValues):
    measure_date: date


class MeasurementInput(BaseModel):
    animal_id: str
    age_month: int | None = Field(default=None, ge=0)
    current: BodyMeasurementValues
    history: list[MeasurementHistoryItem] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    use_demo_history: bool = False


class MeasurementAnalysisResult(BaseModel):
    animal_id: str
    summary: str
    abnormal_items: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommendation: str
    report: str
    used_demo_history: bool = False
