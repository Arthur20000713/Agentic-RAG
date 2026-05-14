from __future__ import annotations

from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.schemas.measurement import MeasurementInput


MemorySubjectType = Literal["farm", "animal"]
MemorySource = Literal["user_confirmed", "tool_result", "ai_inferred"]
MemoryEventType = Literal["upsert", "supersede", "delete"]


class MemoryFact(BaseModel):
    subject_type: MemorySubjectType
    subject_id: str
    fact_type: str
    value: dict[str, Any]
    source: MemorySource
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryEvent(BaseModel):
    event_id: str
    subject_type: MemorySubjectType
    subject_id: str
    event_type: MemoryEventType
    source: Literal["user_confirmed", "tool_result"]
    payload: dict[str, Any]
    supersedes_event_id: str | None = None


class MemoryService:
    allowed_sources = {"user_confirmed", "tool_result"}

    def __init__(self, event_writer: Callable[[MemoryEvent], object] | None = None) -> None:
        self.event_writer = event_writer

    def maybe_write_memory(self, fact: MemoryFact) -> MemoryEvent | None:
        if fact.source not in self.allowed_sources:
            return None
        event = MemoryEvent(
            event_id=f"mem_{uuid4().hex}",
            subject_type=fact.subject_type,
            subject_id=fact.subject_id,
            event_type="upsert",
            source=fact.source,
            payload={
                "fact_type": fact.fact_type,
                "value": fact.value,
                "metadata": fact.metadata,
            },
        )
        if self.event_writer is not None:
            self.event_writer(event)
        return event


def build_measurement_memory_fact(
    measurement: MeasurementInput,
    *,
    source: MemorySource = "user_confirmed",
    metadata: dict[str, Any] | None = None,
) -> MemoryFact:
    current_values = {
        field: value
        for field, value in measurement.current.model_dump().items()
        if value is not None
    }
    value: dict[str, Any] = {"current": current_values}
    if measurement.age_month is not None:
        value["age_month"] = measurement.age_month
    if measurement.confidence is not None:
        value["confidence"] = measurement.confidence

    return MemoryFact(
        subject_type="animal",
        subject_id=measurement.animal_id,
        fact_type="measurement",
        value=value,
        source=source,
        metadata=metadata or {},
    )
