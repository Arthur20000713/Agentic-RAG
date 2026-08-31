from __future__ import annotations

import time

from backend.app.agent.rag_answer_policy import NO_ANSWER_TEXT
from backend.app.agent.state import MultiAgentState
from backend.app.schemas.planning import (
    MAX_REPLANS,
    ExecutionFailure,
    PlanStep,
    ReplanRecord,
    TaskPlan,
)


class ReplanAgent:
    def replan(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        failure = state.execution_failure
        plan = state.task_plan
        if failure is None or plan is None or not failure.retryable:
            return state
        if state.replan_count >= MAX_REPLANS:
            state.execution_failure = ExecutionFailure(
                category="permanent",
                error_code="REPLAN_LIMIT_REACHED",
                step_id=failure.step_id,
                retryable=False,
                reason="replanning budget is exhausted",
            )
            state.draft_answer = NO_ANSWER_TEXT
            state.evidence_status = "low_confidence"
            state.retrieved_contexts.clear()
            self._trace(state, "limit_reached", started_at)
            return state

        completed_ids = {
            result.step_id for result in state.step_results if result.status == "succeeded"
        }
        preserved = [step for step in plan.steps if step.step_id in completed_ids]
        revision = plan.revision + 1
        fallback_id = f"fallback_r{revision}"
        fallback = PlanStep(
            step_id=fallback_id,
            action="safe_fallback",
            description="Return a safe limitation after the recoverable execution path failed.",
            depends_on=[step.step_id for step in preserved],
            arguments={"reason_code": failure.error_code},
            completion_criteria=["safe fallback answer is recorded"],
        )
        state.task_plan = TaskPlan(
            plan_id=plan.plan_id,
            goal=plan.goal,
            steps=[*preserved, fallback],
            completion_criteria=plan.completion_criteria,
            source="replan",
            revision=revision,
        )
        state.replan_count += 1
        state.replan_history.append(
            ReplanRecord(
                revision=revision,
                failure_code=failure.error_code,
                preserved_completed_steps=[step.step_id for step in preserved],
                replacement_step_ids=[fallback_id],
            )
        )
        state.errors = [
            error for error in state.errors if error.error_code != failure.error_code
        ]
        state.execution_failure = None
        state.plan_verification = None
        state.current_step_id = None
        self._trace(state, "success", started_at)
        return state

    def _trace(self, state: MultiAgentState, status: str, started_at: float) -> None:
        failure_code = (
            state.replan_history[-1].failure_code
            if state.replan_history and status == "success"
            else state.execution_failure.error_code if state.execution_failure is not None else None
        )
        state.agent_trace.append(
            {
                "node": "replan",
                "status": status,
                "plan_id": state.task_plan.plan_id if state.task_plan is not None else None,
                "revision": state.task_plan.revision if state.task_plan is not None else None,
                "replan_count": state.replan_count,
                "failure_code": failure_code,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )


__all__ = ["ReplanAgent"]
