from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from backend.app.agent.state import MultiAgentState
from backend.app.schemas.planning import (
    MAX_STEP_ATTEMPTS,
    MAX_TOTAL_STEP_EXECUTIONS,
    ExecutionFailure,
    PlanStep,
    StepExecutionResult,
)


@dataclass(frozen=True)
class ActionOutcome:
    output_ref: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False

    @property
    def succeeded(self) -> bool:
        return self.output_ref is not None and self.error_code is None

    @classmethod
    def success(cls, output_ref: str) -> ActionOutcome:
        return cls(output_ref=output_ref)

    @classmethod
    def failure(
        cls,
        error_code: str,
        error_message: str,
        *,
        retryable: bool,
    ) -> ActionOutcome:
        return cls(
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )


StepHandler = Callable[
    [MultiAgentState, PlanStep, str],
    ActionOutcome | Awaitable[ActionOutcome],
]


@dataclass(frozen=True)
class ExecutionHandlers:
    understand_disease: StepHandler
    query_knowledge_hub: StepHandler
    compose_grounded_answer: StepHandler
    safe_fallback: StepHandler


class ExecutorAgent:
    def __init__(self, handlers: ExecutionHandlers) -> None:
        self.handlers = handlers

    async def execute_next(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        plan = state.task_plan
        if plan is None:
            self._record_failure(
                state,
                error_code="PLAN_MISSING",
                reason="task plan is required before execution",
                retryable=False,
            )
            return state
        if state.execution_failure is not None:
            return state

        finished_step_ids = {result.step_id for result in state.step_results}
        succeeded_step_ids = {
            result.step_id for result in state.step_results if result.status == "succeeded"
        }
        pending = [step for step in plan.steps if step.step_id not in finished_step_ids]
        if not pending:
            state.current_step_id = None
            return state
        runnable = [step for step in pending if set(step.depends_on) <= succeeded_step_ids]
        if not runnable:
            self._record_failure(
                state,
                error_code="PLAN_DEADLOCK",
                reason="no pending step has satisfied dependencies",
                retryable=False,
            )
            return state

        step = runnable[0]
        state.current_step_id = step.step_id
        attempt = sum(result.step_id == step.step_id for result in state.step_results) + 1
        if state.execution_count >= MAX_TOTAL_STEP_EXECUTIONS:
            self._record_failure(
                state,
                error_code="STEP_EXECUTION_LIMIT_REACHED",
                reason="total step execution budget is exhausted",
                retryable=False,
                step_id=step.step_id,
            )
            return state
        if attempt > MAX_STEP_ATTEMPTS:
            self._record_failure(
                state,
                error_code="STEP_ATTEMPT_LIMIT_REACHED",
                reason="step attempt budget is exhausted",
                retryable=False,
                step_id=step.step_id,
            )
            return state

        operation_key = (
            f"{state.request_id or state.session_id}:{plan.plan_id}:{step.step_id}:{attempt}"
        )
        state.execution_count += 1
        try:
            outcome = self._handler(step)(state, step, operation_key)
            if inspect.isawaitable(outcome):
                outcome = await outcome
        except Exception as exc:
            outcome = ActionOutcome.failure(
                "STEP_EXECUTION_ERROR",
                str(exc) or exc.__class__.__name__,
                retryable=False,
            )
        if not isinstance(outcome, ActionOutcome):
            outcome = ActionOutcome.failure(
                "STEP_HANDLER_RESULT_INVALID",
                "step handler must return ActionOutcome",
                retryable=False,
            )

        if outcome.succeeded:
            result = StepExecutionResult(
                step_id=step.step_id,
                status="succeeded",
                output_ref=outcome.output_ref,
                attempt=attempt,
            )
            status = "success"
        else:
            result = StepExecutionResult(
                step_id=step.step_id,
                status="failed",
                error_code=outcome.error_code or "STEP_EXECUTION_FAILED",
                error_message=outcome.error_message,
                retryable=outcome.retryable,
                attempt=attempt,
            )
            self._record_failure(
                state,
                error_code=result.error_code or "STEP_EXECUTION_FAILED",
                reason=result.error_message or "step execution failed",
                retryable=result.retryable,
                step_id=step.step_id,
            )
            status = "failed"
        state.step_results.append(result)
        state.agent_trace.append(
            {
                "node": "executor",
                "status": status,
                "plan_id": plan.plan_id,
                "revision": plan.revision,
                "step_id": step.step_id,
                "action": step.action,
                "attempt": attempt,
                "operation_key": operation_key,
                "error_code": result.error_code,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    def _handler(self, step: PlanStep) -> StepHandler:
        if step.action == "understand_disease":
            return self.handlers.understand_disease
        if step.action == "query_knowledge_hub":
            return self.handlers.query_knowledge_hub
        if step.action == "compose_grounded_answer":
            return self.handlers.compose_grounded_answer
        if step.action == "safe_fallback":
            return self.handlers.safe_fallback
        raise ValueError(f"unsupported planning action: {step.action}")

    def _record_failure(
        self,
        state: MultiAgentState,
        *,
        error_code: str,
        reason: str,
        retryable: bool,
        step_id: str | None = None,
    ) -> None:
        state.execution_failure = ExecutionFailure(
            category="recoverable" if retryable else "permanent",
            error_code=error_code,
            step_id=step_id,
            retryable=retryable,
            reason=reason,
        )


__all__ = ["ActionOutcome", "ExecutionHandlers", "ExecutorAgent", "StepHandler"]
