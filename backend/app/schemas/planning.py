from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_PLAN_STEPS = 3
MAX_REPLANS = 2
MAX_STEP_ATTEMPTS = 2
MAX_TOTAL_STEP_EXECUTIONS = 8

PlanningAction = Literal[
    "understand_disease",
    "query_knowledge_hub",
    "compose_grounded_answer",
    "safe_fallback",
]
PlanSource = Literal["model", "fallback", "replan"]
StepStatus = Literal["succeeded", "failed", "skipped"]
FailureCategory = Literal[
    "recoverable",
    "insufficient_evidence",
    "invalid_plan",
    "permanent",
    "safety",
    "deadline",
]


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    action: PlanningAction
    description: str = Field(min_length=1, max_length=240)
    depends_on: list[str] = Field(default_factory=list, max_length=MAX_PLAN_STEPS - 1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    completion_criteria: list[str] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_step_contract(self) -> PlanStep:
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("step dependencies must be unique")
        if self.step_id in self.depends_on:
            raise ValueError("step cannot depend on itself")

        if self.action == "query_knowledge_hub":
            if set(self.arguments) != {"query_source", "top_k"}:
                raise ValueError("retrieval arguments must be query_source and top_k")
            if self.arguments["query_source"] not in {"rag_query", "normalized_query"}:
                raise ValueError("query_source must reference a trusted state field")
            top_k = self.arguments["top_k"]
            if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
                raise ValueError("top_k must be an integer between 1 and 20")
        elif self.action == "safe_fallback":
            if set(self.arguments).difference({"reason_code"}):
                raise ValueError("safe_fallback accepts only reason_code")
            if "reason_code" in self.arguments and not isinstance(self.arguments["reason_code"], str):
                raise ValueError("reason_code must be a string")
        elif self.arguments:
            raise ValueError(f"{self.action} does not accept arguments")
        return self


class TaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1, max_length=96, pattern=r"^plan_[a-z0-9_]+$")
    goal: str = Field(min_length=1, max_length=500)
    steps: list[PlanStep] = Field(min_length=1, max_length=MAX_PLAN_STEPS)
    completion_criteria: list[str] = Field(min_length=1, max_length=3)
    source: PlanSource
    revision: int = Field(ge=1, le=MAX_REPLANS + 1)

    @model_validator(mode="after")
    def validate_dag(self) -> TaskPlan:
        step_ids = [step.step_id for step in self.steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("step IDs must be unique")

        known = set(step_ids)
        for step in self.steps:
            missing = set(step.depends_on).difference(known)
            if missing:
                raise ValueError(f"unknown step dependencies: {sorted(missing)}")

        dependencies = {step.step_id: set(step.depends_on) for step in self.steps}
        remaining = set(step_ids)
        resolved: set[str] = set()
        while remaining:
            runnable = {step_id for step_id in remaining if dependencies[step_id] <= resolved}
            if not runnable:
                raise ValueError("plan dependencies contain a cycle")
            remaining.difference_update(runnable)
            resolved.update(runnable)

        retrieval_count = sum(step.action == "query_knowledge_hub" for step in self.steps)
        if retrieval_count > 1:
            raise ValueError("stage two allows at most one knowledge retrieval")
        return self


class StepExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    status: StepStatus
    output_ref: str | None = Field(default=None, min_length=1, max_length=128)
    error_code: str | None = Field(default=None, min_length=1, max_length=96)
    error_message: str | None = Field(default=None, max_length=500)
    retryable: bool = False
    attempt: int = Field(ge=1, le=MAX_STEP_ATTEMPTS)

    @model_validator(mode="after")
    def validate_result_contract(self) -> StepExecutionResult:
        if self.status == "succeeded" and self.output_ref is None:
            raise ValueError("successful steps require output_ref")
        if self.status == "failed" and self.error_code is None:
            raise ValueError("failed steps require error_code")
        if self.status != "failed" and (self.error_code is not None or self.retryable):
            raise ValueError("only failed steps may contain error details")
        return self


class ExecutionFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FailureCategory
    error_code: str = Field(min_length=1, max_length=96)
    step_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    retryable: bool
    reason: str = Field(min_length=1, max_length=500)


class ReplanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=2, le=MAX_REPLANS + 1)
    failure_code: str = Field(min_length=1, max_length=96)
    preserved_completed_steps: list[str] = Field(default_factory=list, max_length=MAX_PLAN_STEPS)
    replacement_step_ids: list[str] = Field(default_factory=list, max_length=MAX_PLAN_STEPS)


__all__ = [
    "ExecutionFailure",
    "FailureCategory",
    "MAX_PLAN_STEPS",
    "MAX_REPLANS",
    "MAX_STEP_ATTEMPTS",
    "MAX_TOTAL_STEP_EXECUTIONS",
    "PlanSource",
    "PlanStep",
    "PlanningAction",
    "ReplanRecord",
    "StepExecutionResult",
    "StepStatus",
    "TaskPlan",
]
