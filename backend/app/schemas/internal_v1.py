from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ID_PATTERN = r"^[A-Za-z0-9._:-]+$"
COLLECTION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
DOCUMENT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
OBJECT_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$"


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class InternalModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class OpaqueContext(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="allow",
    )

    schema_version: int = Field(ge=1)
    slots: dict[str, Any] = Field(default_factory=dict)


class ConversationHistoryItem(InternalModel):
    turn_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    role: Literal["USER", "ASSISTANT"]
    content: str = Field(min_length=1, max_length=12000)
    created_at: datetime | None = None


class AnimalSnapshot(InternalModel):
    animal_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    species: str = Field(min_length=1, max_length=64)
    breed: str | None = Field(default=None, max_length=128)
    sex: str | None = Field(default=None, max_length=32)
    birth_date: date | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(InternalModel):
    request_id: str = Field(min_length=8, max_length=128, pattern=ID_PATTERN)
    operation_id: str = Field(min_length=8, max_length=128, pattern=ID_PATTERN)
    conversation_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    user_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    query: str = Field(min_length=1, max_length=4000)
    animal_snapshot: AnimalSnapshot | None = None
    history: list[ConversationHistoryItem] = Field(max_length=20)
    context: OpaqueContext
    context_version: int = Field(ge=0)
    deadline_ms: int = Field(ge=1000, le=60000)

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class BodyMeasurementValues(InternalModel):
    body_height_cm: float | None = Field(default=None, ge=0)
    body_length_cm: float | None = Field(default=None, ge=0)
    chest_girth_cm: float | None = Field(default=None, ge=0)
    chest_depth_cm: float | None = Field(default=None, ge=0)
    chest_width_cm: float | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_measurement(self) -> "BodyMeasurementValues":
        fields = (
            self.body_height_cm,
            self.body_length_cm,
            self.chest_girth_cm,
            self.chest_depth_cm,
            self.chest_width_cm,
            self.weight_kg,
        )
        if not any(value is not None for value in fields):
            raise ValueError("at least one measurement value is required")
        return self


class MeasurementHistoryItem(BodyMeasurementValues):
    measure_date: date


class MeasurementAnalyzeRequest(InternalModel):
    request_id: str = Field(min_length=8, max_length=128, pattern=ID_PATTERN)
    operation_id: str = Field(min_length=8, max_length=128, pattern=ID_PATTERN)
    user_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    animal_snapshot: AnimalSnapshot
    age_month: int | None = Field(default=None, ge=0)
    current: BodyMeasurementValues
    history: list[MeasurementHistoryItem] = Field(max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    use_demo_history: bool = False
    deadline_ms: int = Field(ge=1000, le=30000)


class KnowledgeIngestionRequest(InternalModel):
    request_id: str = Field(min_length=8, max_length=128, pattern=ID_PATTERN)
    operation_id: str = Field(min_length=8, max_length=128, pattern=ID_PATTERN)
    user_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    document_id: str = Field(min_length=1, max_length=256, pattern=DOCUMENT_ID_PATTERN)
    collection: str = Field(min_length=1, max_length=128, pattern=COLLECTION_PATTERN)
    object_key: str = Field(min_length=1, max_length=512, pattern=OBJECT_KEY_PATTERN)
    file_name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1, le=104857600)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    force: Literal[False] = False


class ChatOutcome(StrEnum):
    ANSWERED = "ANSWERED"
    NEEDS_FOLLOW_UP = "NEEDS_FOLLOW_UP"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    SAFETY_REFUSAL = "SAFETY_REFUSAL"


class EvidenceStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_REQUIRED = "NOT_REQUIRED"


class SourceCitation(InternalModel):
    collection: str = Field(min_length=1, max_length=128, pattern=COLLECTION_PATTERN)
    document_id: str | int
    title: str = Field(min_length=1, max_length=512)
    source_uri: str | None = None
    page: int | None = Field(default=None, ge=1)
    section_title: str | None = Field(default=None, max_length=512)
    chunk_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    score: float = Field(ge=0, le=1)


class SafetyDecision(InternalModel):
    decision: Literal["ALLOWED", "REFUSED"]
    reason_code: str | None = Field(default=None, max_length=128)


class ChatResponse(InternalModel):
    request_id: str
    operation_id: str
    run_id: str
    outcome: ChatOutcome
    answer: str = Field(min_length=1, max_length=30000)
    intent: str = Field(min_length=1, max_length=128)
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    evidence_status: EvidenceStatus
    sources: list[SourceCitation]
    follow_up_questions: list[str] = Field(max_length=10)
    tools_used: list[str]
    safety: SafetyDecision
    next_context: OpaqueContext
    context_version: int = Field(ge=1)
    trace_id: str


class MeasurementAnalysis(InternalModel):
    animal_id: str
    summary: str
    abnormal_items: list[str]
    evidence: list[str]
    recommendation: str
    report: str
    used_demo_history: bool


class MeasurementAnalyzeResponse(InternalModel):
    request_id: str
    operation_id: str
    run_id: str
    outcome: Literal["ANALYZED", "INSUFFICIENT_DATA", "LOW_CONFIDENCE"]
    result: MeasurementAnalysis
    trace_id: str


class ErrorDetail(InternalModel):
    code: str
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(InternalModel):
    request_id: str
    operation_id: str | None = None
    error: ErrorDetail


class KnowledgeIngestionAccepted(InternalModel):
    request_id: str
    operation_id: str
    run_id: str
    type: Literal["DOCUMENT_INDEX"] = "DOCUMENT_INDEX"
    status: Literal["ACCEPTED", "RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"]
    submitted_at: datetime


class DocumentIndexResult(InternalModel):
    document_id: str = Field(min_length=1, max_length=256, pattern=DOCUMENT_ID_PATTERN)
    rag_document_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    collection: str = Field(min_length=1, max_length=128, pattern=COLLECTION_PATTERN)
    indexed: bool
    skipped: bool
    chunk_count: int | None = Field(default=None, ge=0)
    execution_mode: Literal["FAKE", "REAL"]


class ChatRun(InternalModel):
    request_id: str
    operation_id: str
    run_id: str
    type: Literal["AI_CHAT"] = "AI_CHAT"
    status: Literal["RUNNING", "SUCCEEDED", "FAILED"]
    result: ChatResponse | None = None
    error: ErrorDetail | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_status_payload(self) -> "ChatRun":
        valid = {
            "RUNNING": self.result is None and self.error is None,
            "SUCCEEDED": self.result is not None and self.error is None,
            "FAILED": self.result is None and self.error is not None,
        }
        if not valid[self.status]:
            raise ValueError("chat run result/error does not match status")
        return self


class AiOperation(InternalModel):
    request_id: str
    operation_id: str
    run_id: str
    type: Literal["DOCUMENT_INDEX"] = "DOCUMENT_INDEX"
    status: Literal["ACCEPTED", "RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"]
    progress: int = Field(ge=0, le=100)
    result: DocumentIndexResult | None = None
    error: ErrorDetail | None = None
    created_at: datetime
    started_at: datetime | None = None
    updated_at: datetime
    finished_at: datetime | None = None
    expires_at: datetime

    @model_validator(mode="after")
    def validate_status_payload(self) -> "AiOperation":
        pending = self.status in {"ACCEPTED", "RUNNING"}
        succeeded = self.status == "SUCCEEDED"
        failed = self.status in {"FAILED", "TIMED_OUT", "CANCELLED"}
        valid = (
            (pending and self.result is None and self.error is None and self.finished_at is None)
            or (succeeded and self.result is not None and self.error is None and self.progress == 100)
            or (failed and self.result is None and self.error is not None and self.progress == 100)
        )
        if not valid:
            raise ValueError("operation result/error does not match status")
        return self


class CollectionSummary(InternalModel):
    name: str
    description: str | None = None
    document_count: int | None = Field(default=None, ge=0)
    updated_at: datetime | None = None


class CollectionListResponse(InternalModel):
    request_id: str
    collections: list[CollectionSummary]
    raw_response_id: str | None = None


class DocumentSummaryResponse(InternalModel):
    request_id: str
    collection: str
    document_id: str
    title: str | None = None
    summary: str = Field(min_length=1)
    tags: list[str]
    source: str | None = None
    chunk_count: int | None = Field(default=None, ge=0)
    source_uri_prefix: str
    raw_response_id: str | None = None


class HealthCheck(InternalModel):
    status: Literal["UP", "DOWN"]
    code: str | None = None
    message: str | None = None


class LivenessResponse(InternalModel):
    request_id: str
    status: Literal["UP"] = "UP"
    service: Literal["livestock-ai-service"] = "livestock-ai-service"
    version: str
    timestamp: datetime


class ReadinessResponse(InternalModel):
    request_id: str
    status: Literal["READY", "NOT_READY"]
    checks: dict[str, HealthCheck]
    timestamp: datetime
