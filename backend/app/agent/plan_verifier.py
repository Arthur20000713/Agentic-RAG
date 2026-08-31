from __future__ import annotations

import time

from backend.app.agent.state import MultiAgentState
from backend.app.schemas.planning import (
    ExecutionFailure,
    PlanStep,
    PlanVerificationResult,
    StepExecutionResult,
)


class PlanVerifier:
    def verify(self, state: MultiAgentState) -> PlanVerificationResult:
        started_at = time.perf_counter()
        if state.task_plan is None:
            return self._record(
                state,
                PlanVerificationResult(
                    decision="terminal",
                    error_code="PLAN_MISSING",
                    reason="task plan is missing",
                ),
                started_at,
            )
        if state.execution_failure is not None:
            failure = state.execution_failure
            return self._record(
                state,
                PlanVerificationResult(
                    decision="replan" if failure.retryable else "terminal",
                    step_id=failure.step_id,
                    error_code=failure.error_code,
                    reason=failure.reason,
                ),
                started_at,
            )

        latest = state.step_results[-1] if state.step_results else None
        if latest is not None and latest.status == "succeeded":
            step = next(
                item for item in state.task_plan.steps if item.step_id == latest.step_id
            )
            if not self._has_required_output(state, step, latest):
                state.execution_failure = ExecutionFailure(
                    category="recoverable",
                    error_code="STEP_OUTPUT_MISSING",
                    step_id=step.step_id,
                    retryable=True,
                    reason=f"required output is missing for action {step.action}",
                )
                return self._record(
                    state,
                    PlanVerificationResult(
                        decision="replan",
                        step_id=step.step_id,
                        error_code="STEP_OUTPUT_MISSING",
                        reason=state.execution_failure.reason,
                    ),
                    started_at,
                )

        succeeded = {
            result.step_id for result in state.step_results if result.status == "succeeded"
        }
        if all(step.step_id in succeeded for step in state.task_plan.steps):
            result = PlanVerificationResult(
                decision="goal",
                step_id=latest.step_id if latest is not None else None,
                reason="all plan steps and the task goal are satisfied",
            )
        else:
            result = PlanVerificationResult(
                decision="next",
                step_id=latest.step_id if latest is not None else None,
                reason="the next dependency-ready step may execute",
            )
        return self._record(state, result, started_at)

    def _has_required_output(
        self,
        state: MultiAgentState,
        step: PlanStep,
        result: StepExecutionResult,
    ) -> bool:
        expected_ref = {
            "understand_disease": "disease_assessment",
            "query_knowledge_hub": "livestock_rag_search",
            "compose_grounded_answer": "draft_answer",
            "safe_fallback": "draft_answer",
        }[step.action]
        if result.output_ref != expected_ref:
            return False
        if step.action == "understand_disease":
            return isinstance(state.disease_assessment, dict)
        if step.action == "query_knowledge_hub":
            return isinstance(state.tool_results.get("livestock_rag_search"), dict)
        return isinstance(state.draft_answer, str) and bool(state.draft_answer.strip())

    def _record(
        self,
        state: MultiAgentState,
        result: PlanVerificationResult,
        started_at: float,
    ) -> PlanVerificationResult:
        state.plan_verification = result
        state.agent_trace.append(
            {
                "node": "plan_verifier",
                "status": "success" if result.decision in {"next", "goal"} else "failed",
                "plan_id": state.task_plan.plan_id if state.task_plan is not None else None,
                "revision": state.task_plan.revision if state.task_plan is not None else None,
                "step_id": result.step_id,
                "decision": result.decision,
                "error_code": result.error_code,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return result


__all__ = ["PlanVerifier"]
