from __future__ import annotations

from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


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

    def __init__(self, event_writer: Callable[[MemoryEvent], None] | None = None) -> None:
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
