from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IntentType = Literal[
    "assistant_intro",
    "general_qa",
    "disease_consultation",
    "measurement_analysis",
    "out_of_scope",
]
RiskLevel = Literal["low", "medium", "high", "emergency"]


class RetrievedContext(BaseModel):
    chunk_id: str
    document_id: str | int | None = None
    title: str
    content: str
    page: int | None = None
    section_title: str | None = None
    score: float
    source_type: str | None = None


class AgentToolError(BaseModel):
    tool_name: str
    error_code: str
    message: str


class AgentState(BaseModel):
    session_id: str
    user_query: str
    normalized_query: str | None = None
    intent: IntentType | None = None
    intent_confidence: float | None = None
    risk_level: RiskLevel | None = None
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[AgentToolError] = Field(default_factory=list)
    draft_answer: str | None = None
    final_answer: str | None = None
    need_follow_up: bool = False
    follow_up_questions: list[str] = Field(default_factory=list)
