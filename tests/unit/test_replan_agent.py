from __future__ import annotations

from backend.app.agent.replan_agent import ReplanAgent
from backend.app.agent.state import MultiAgentState
from backend.app.schemas.planning import (
    MAX_REPLANS,
    ExecutionFailure,
    StepExecutionResult,
    TaskPlan,
)


def _plan() -> TaskPlan:
    return TaskPlan.model_validate(
        {
            "plan_id": "plan_replan_test",
            "goal": "Answer with grounded evidence.",
            "steps": [
                {
                    "step_id": "retrieve",
                    "action": "query_knowledge_hub",
                    "description": "Retrieve evidence.",
                    "arguments": {"query_source": "normalized_query", "top_k": 4},
                    "completion_criteria": ["retrieval status is recorded"],
                },
                {
                    "step_id": "compose",
                    "action": "compose_grounded_answer",
                    "description": "Compose the answer.",
                    "depends_on": ["retrieve"],
                    "completion_criteria": ["draft answer is recorded"],
                },
            ],
            "completion_criteria": ["answer is ready for final verification"],
            "source": "fallback",
            "revision": 1,
        }
    )


def _failed_state(*, completed_retrieve: bool = False) -> MultiAgentState:
    results = []
    failed_step = "retrieve"
    if completed_retrieve:
        results.append(
            StepExecutionResult(
                step_id="retrieve",
                status="succeeded",
                output_ref="livestock_rag_search",
                attempt=1,
            )
        )
        failed_step = "compose"
    results.append(
        StepExecutionResult(
            step_id=failed_step,
            status="failed",
            error_code="STEP_TRANSIENT",
            error_message="controlled failure",
            retryable=True,
            attempt=2,
        )
    )
    return MultiAgentState(
        session_id="session_replan",
        request_id="request_replan",
        user_query="livestock question",
        normalized_query="livestock question",
        intent="general_qa",
        task_plan=_plan(),
        step_results=results,
        execution_failure=ExecutionFailure(
            category="recoverable",
            error_code="STEP_TRANSIENT",
            step_id=failed_step,
            retryable=True,
            reason="controlled failure",
        ),
    )


def test_replan_replaces_failed_chain_and_preserves_completed_steps() -> None:
    state = _failed_state(completed_retrieve=True)

    ReplanAgent().replan(state)

    assert state.task_plan is not None
    assert state.task_plan.revision == 2
    assert state.task_plan.source == "replan"
    assert [step.step_id for step in state.task_plan.steps] == ["retrieve", "fallback_r2"]
    assert state.task_plan.steps[-1].depends_on == ["retrieve"]
    assert state.replan_count == 1
    assert state.execution_failure is None
    assert state.plan_verification is None
    assert state.replan_history[0].preserved_completed_steps == ["retrieve"]
    assert state.replan_history[0].replacement_step_ids == ["fallback_r2"]


def test_replan_without_completed_steps_uses_single_safe_fallback() -> None:
    state = _failed_state()

    ReplanAgent().replan(state)

    assert state.task_plan is not None
    assert [step.action for step in state.task_plan.steps] == ["safe_fallback"]
    assert state.task_plan.steps[0].arguments == {"reason_code": "STEP_TRANSIENT"}


def test_replan_rejects_non_retryable_failure() -> None:
    state = _failed_state()
    state.execution_failure = state.execution_failure.model_copy(
        update={"category": "permanent", "retryable": False}
    )

    ReplanAgent().replan(state)

    assert state.task_plan is not None
    assert state.task_plan.revision == 1
    assert state.replan_count == 0
    assert state.execution_failure.error_code == "STEP_TRANSIENT"


def test_replan_limit_terminates_with_safe_no_answer() -> None:
    state = _failed_state()
    state.replan_count = MAX_REPLANS

    ReplanAgent().replan(state)

    assert state.replan_count == MAX_REPLANS
    assert state.execution_failure is not None
    assert state.execution_failure.retryable is False
    assert state.execution_failure.error_code == "REPLAN_LIMIT_REACHED"
    assert state.draft_answer
    assert state.agent_trace[-1]["node"] == "replan"
    assert state.agent_trace[-1]["status"] == "limit_reached"
