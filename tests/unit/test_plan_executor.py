from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.plan_executor import ActionOutcome, ExecutionHandlers, ExecutorAgent
from backend.app.agent.plan_verifier import PlanVerifier
from backend.app.agent.state import MultiAgentState
from backend.app.schemas.planning import MAX_TOTAL_STEP_EXECUTIONS, TaskPlan


def _disease_plan() -> TaskPlan:
    return TaskPlan.model_validate(
        {
            "plan_id": "plan_executor_test",
            "goal": "Answer a disease consultation with grounded evidence.",
            "steps": [
                {
                    "step_id": "understand",
                    "action": "understand_disease",
                    "description": "Understand the case.",
                    "completion_criteria": ["disease assessment is recorded"],
                },
                {
                    "step_id": "retrieve",
                    "action": "query_knowledge_hub",
                    "description": "Retrieve evidence.",
                    "depends_on": ["understand"],
                    "arguments": {"query_source": "rag_query", "top_k": 4},
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


def _state() -> MultiAgentState:
    return MultiAgentState(
        session_id="session_executor",
        request_id="request_executor",
        user_query="A calf has diarrhea.",
        normalized_query="calf diarrhea",
        intent="disease_consultation",
        task_plan=_disease_plan(),
    )


def test_executor_runs_one_ready_step_at_a_time_and_verifies_goal() -> None:
    calls: list[tuple[str, str]] = []

    def understand(state, step, operation_key):  # noqa: ANN001
        calls.append((step.step_id, operation_key))
        state.disease_assessment = {"status": "complete"}
        state.rag_query = "calf diarrhea"
        return ActionOutcome.success("disease_assessment")

    async def retrieve(state, step, operation_key):  # noqa: ANN001
        calls.append((step.step_id, operation_key))
        state.tool_results["livestock_rag_search"] = {"status": "success", "hits": [{}]}
        state.evidence_status = "success"
        return ActionOutcome.success("livestock_rag_search")

    def compose(state, step, operation_key):  # noqa: ANN001
        calls.append((step.step_id, operation_key))
        state.draft_answer = "Grounded answer [1]."
        return ActionOutcome.success("draft_answer")

    state = _state()
    executor = ExecutorAgent(
        ExecutionHandlers(
            understand_disease=understand,
            query_knowledge_hub=retrieve,
            compose_grounded_answer=compose,
            safe_fallback=lambda *_: ActionOutcome.success("draft_answer"),
        )
    )
    verifier = PlanVerifier()

    decisions = []
    for _ in range(3):
        asyncio.run(executor.execute_next(state))
        decisions.append(verifier.verify(state).decision)

    assert [item[0] for item in calls] == ["understand", "retrieve", "compose"]
    assert all("request_executor:plan_executor_test:" in item[1] for item in calls)
    assert decisions == ["next", "next", "goal"]
    assert state.execution_count == 3
    assert [result.status for result in state.step_results] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]


def test_plan_verifier_requests_replan_for_retryable_step_failure() -> None:
    state = _state()
    executor = ExecutorAgent(
        ExecutionHandlers(
            understand_disease=lambda *_: ActionOutcome.failure(
                "MODEL_SCHEMA_INVALID",
                "understanding output was invalid",
                retryable=True,
            ),
            query_knowledge_hub=lambda *_: ActionOutcome.success("livestock_rag_search"),
            compose_grounded_answer=lambda *_: ActionOutcome.success("draft_answer"),
            safe_fallback=lambda *_: ActionOutcome.success("draft_answer"),
        )
    )

    asyncio.run(executor.execute_next(state))
    verification = PlanVerifier().verify(state)

    assert verification.decision == "replan"
    assert verification.error_code == "MODEL_SCHEMA_INVALID"
    assert state.execution_failure is not None
    assert state.execution_failure.category == "recoverable"


def test_plan_verifier_terminates_permanent_step_failure() -> None:
    state = _state()
    executor = ExecutorAgent(
        ExecutionHandlers(
            understand_disease=lambda *_: ActionOutcome.failure(
                "TRUSTED_INPUT_MISSING",
                "required animal context is missing",
                retryable=False,
            ),
            query_knowledge_hub=lambda *_: ActionOutcome.success("livestock_rag_search"),
            compose_grounded_answer=lambda *_: ActionOutcome.success("draft_answer"),
            safe_fallback=lambda *_: ActionOutcome.success("draft_answer"),
        )
    )

    asyncio.run(executor.execute_next(state))
    verification = PlanVerifier().verify(state)

    assert verification.decision == "terminal"
    assert verification.error_code == "TRUSTED_INPUT_MISSING"
    assert state.execution_failure is not None
    assert state.execution_failure.category == "permanent"


def test_plan_verifier_rejects_success_without_required_state_output() -> None:
    state = _state()
    executor = ExecutorAgent(
        ExecutionHandlers(
            understand_disease=lambda *_: ActionOutcome.success("disease_assessment"),
            query_knowledge_hub=lambda *_: ActionOutcome.success("livestock_rag_search"),
            compose_grounded_answer=lambda *_: ActionOutcome.success("draft_answer"),
            safe_fallback=lambda *_: ActionOutcome.success("draft_answer"),
        )
    )

    asyncio.run(executor.execute_next(state))
    verification = PlanVerifier().verify(state)

    assert verification.decision == "replan"
    assert verification.error_code == "STEP_OUTPUT_MISSING"
    assert state.execution_failure is not None
    assert state.execution_failure.step_id == "understand"


def test_executor_stops_before_handler_when_total_budget_is_exhausted() -> None:
    state = _state()
    state.execution_count = MAX_TOTAL_STEP_EXECUTIONS
    call_count = 0

    def forbidden(*_: Any) -> ActionOutcome:
        nonlocal call_count
        call_count += 1
        return ActionOutcome.success("disease_assessment")

    executor = ExecutorAgent(
        ExecutionHandlers(
            understand_disease=forbidden,
            query_knowledge_hub=forbidden,
            compose_grounded_answer=forbidden,
            safe_fallback=forbidden,
        )
    )

    asyncio.run(executor.execute_next(state))
    verification = PlanVerifier().verify(state)

    assert call_count == 0
    assert verification.decision == "terminal"
    assert verification.error_code == "STEP_EXECUTION_LIMIT_REACHED"


def test_executor_rejects_invalid_handler_result_without_running_next_step() -> None:
    state = _state()
    executor = ExecutorAgent(
        ExecutionHandlers(
            understand_disease=lambda *_: {"status": "success"},
            query_knowledge_hub=lambda *_: ActionOutcome.success("livestock_rag_search"),
            compose_grounded_answer=lambda *_: ActionOutcome.success("draft_answer"),
            safe_fallback=lambda *_: ActionOutcome.success("draft_answer"),
        )
    )

    asyncio.run(executor.execute_next(state))
    verification = PlanVerifier().verify(state)

    assert verification.decision == "terminal"
    assert verification.error_code == "STEP_HANDLER_RESULT_INVALID"
    assert state.execution_count == 1
