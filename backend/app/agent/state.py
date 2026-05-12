from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.schemas.agent import AgentToolError, IntentType, RetrievedContext


EvidenceStatus = Literal["success", "empty", "low_confidence", "error"]


class MultiAgentState(BaseModel):
    session_id: str
    user_query: str
    normalized_query: str | None = None
    intent: IntentType | None = None
    route_reason: str | None = None
    active_agent: str | None = None
    session_context: dict[str, Any] = Field(default_factory=dict)
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    rag_query: str | None = None
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    evidence_status: EvidenceStatus | None = None
    disease_assessment: dict[str, Any] | None = None
    measurement_report: dict[str, Any] | None = None
    draft_answer: str | None = None
    verification_result: dict[str, Any] | None = None
    safety_result: dict[str, Any] | None = None
    final_answer: str | None = None
    tool_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[AgentToolError] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
