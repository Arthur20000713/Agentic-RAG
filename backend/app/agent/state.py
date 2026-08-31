from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.schemas.agent import AgentToolError, IntentType, RetrievedContext, RiskLevel
from backend.app.schemas.planning import (
    ExecutionFailure,
    MAX_REPLANS,
    PlanVerificationResult,
    ReplanRecord,
    StepExecutionResult,
    TaskPlan,
)


EvidenceStatus = Literal["success", "empty", "low_confidence", "error"]


class MultiAgentState(BaseModel):
    session_id: str
    request_id: str | None = None
    user_query: str
    turn_reset_required: bool = False
    normalized_query: str | None = None
    intent: IntentType | None = None
    risk_level: RiskLevel | None = None
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
    task_plan: TaskPlan | None = None
    current_step_id: str | None = None
    step_results: list[StepExecutionResult] = Field(default_factory=list)
    execution_failure: ExecutionFailure | None = None
    execution_count: int = Field(default=0, ge=0)
    plan_verification: PlanVerificationResult | None = None
    replan_count: int = Field(default=0, ge=0, le=MAX_REPLANS)
    replan_history: list[ReplanRecord] = Field(default_factory=list)
    tool_plan: list[dict[str, Any]] = Field(default_factory=list)
    tool_attempt: int = 0
    tool_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[AgentToolError] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
