from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.schemas.planning import (
    ExecutionFailure,
    PlanStep,
    ReplanRecord,
    StepExecutionResult,
    TaskPlan,
)


def _general_plan() -> dict:
    return {
        "plan_id": "plan_general_001",
        "goal": "Answer the livestock question with grounded evidence.",
        "steps": [
            {
                "step_id": "retrieve",
                "action": "query_knowledge_hub",
                "description": "Retrieve livestock evidence.",
                "arguments": {"query_source": "normalized_query", "top_k": 4},
                "completion_criteria": ["retrieval status is recorded"],
            },
            {
                "step_id": "compose",
                "action": "compose_grounded_answer",
                "description": "Compose an answer from retrieved evidence.",
                "depends_on": ["retrieve"],
                "completion_criteria": ["draft answer is recorded"],
            },
        ],
        "completion_criteria": ["answer is ready for final verification"],
        "source": "fallback",
        "revision": 1,
    }


def test_task_plan_accepts_bounded_general_and_disease_dags() -> None:
    general = TaskPlan.model_validate(_general_plan())
    disease_payload = _general_plan()
    disease_payload["plan_id"] = "plan_disease_001"
    disease_payload["steps"].insert(
        0,
        {
            "step_id": "understand",
            "action": "understand_disease",
            "description": "Extract confirmed disease case facts.",
            "completion_criteria": ["disease assessment is recorded"],
        },
    )
    disease_payload["steps"][1]["depends_on"] = ["understand"]

    disease = TaskPlan.model_validate(disease_payload)

    assert [step.step_id for step in general.steps] == ["retrieve", "compose"]
    assert [step.action for step in disease.steps] == [
        "understand_disease",
        "query_knowledge_hub",
        "compose_grounded_answer",
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["steps"].append(payload["steps"][0].copy()),
        lambda payload: payload["steps"][1].update(depends_on=["missing"]),
        lambda payload: payload["steps"][0].update(depends_on=["retrieve"]),
        lambda payload: (
            payload["steps"][0].update(depends_on=["compose"]),
            payload["steps"][1].update(depends_on=["retrieve"]),
        ),
    ],
)
def test_task_plan_rejects_duplicate_missing_self_and_cyclic_dependencies(mutate) -> None:
    payload = _general_plan()
    mutate(payload)

    with pytest.raises(ValidationError):
        TaskPlan.model_validate(payload)


def test_task_plan_rejects_unknown_actions_extra_fields_and_step_limit() -> None:
    unknown = _general_plan()
    unknown["steps"][0]["action"] = "shell_command"
    unknown["steps"][0]["arguments"] = {"command": "whoami"}
    with pytest.raises(ValidationError):
        TaskPlan.model_validate(unknown)

    extra = _general_plan()
    extra["steps"][0]["tool"] = "query_knowledge_hub"
    with pytest.raises(ValidationError):
        TaskPlan.model_validate(extra)

    too_many = _general_plan()
    too_many["steps"].append(
        {
            "step_id": "fallback",
            "action": "safe_fallback",
            "description": "Return a safe fallback.",
            "depends_on": ["compose"],
            "completion_criteria": ["safe fallback is recorded"],
        }
    )
    too_many["steps"].append(
        {
            "step_id": "fourth",
            "action": "safe_fallback",
            "description": "A fourth step is forbidden.",
            "completion_criteria": ["never executed"],
        }
    )
    with pytest.raises(ValidationError):
        TaskPlan.model_validate(too_many)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query_source": "user supplied query", "top_k": 4},
        {"query_source": "normalized_query", "query": "model rewrite", "top_k": 4},
        {"query_source": "normalized_query", "top_k": 0},
        {"query_source": "normalized_query", "top_k": 21},
        {"query_source": "normalized_query", "top_k": True},
    ],
)
def test_retrieval_step_rejects_unbounded_or_rewritten_query_arguments(arguments) -> None:
    payload = _general_plan()
    payload["steps"][0]["arguments"] = arguments

    with pytest.raises(ValidationError):
        TaskPlan.model_validate(payload)


def test_task_plan_allows_at_most_one_knowledge_retrieval() -> None:
    payload = _general_plan()
    payload["steps"][1] = {
        "step_id": "retrieve_again",
        "action": "query_knowledge_hub",
        "description": "A second retrieval is stage-three work.",
        "depends_on": ["retrieve"],
        "arguments": {"query_source": "rag_query", "top_k": 4},
        "completion_criteria": ["second retrieval status is recorded"],
    }

    with pytest.raises(ValidationError):
        TaskPlan.model_validate(payload)


def test_execution_result_failure_and_replan_contracts_are_strict() -> None:
    succeeded = StepExecutionResult(
        step_id="retrieve",
        status="succeeded",
        output_ref="livestock_rag_search",
        attempt=1,
    )
    failed = StepExecutionResult(
        step_id="retrieve",
        status="failed",
        error_code="RAG_TRANSIENT",
        error_message="temporary failure",
        retryable=True,
        attempt=2,
    )
    failure = ExecutionFailure(
        category="recoverable",
        error_code="RAG_TRANSIENT",
        step_id="retrieve",
        retryable=True,
        reason="temporary failure",
    )
    record = ReplanRecord(
        revision=2,
        failure_code=failure.error_code,
        preserved_completed_steps=["understand"],
        replacement_step_ids=["fallback"],
    )

    assert succeeded.output_ref == "livestock_rag_search"
    assert failed.retryable is True
    assert record.revision == 2

    with pytest.raises(ValidationError):
        StepExecutionResult(step_id="retrieve", status="succeeded", attempt=1)
    with pytest.raises(ValidationError):
        StepExecutionResult(step_id="retrieve", status="failed", attempt=1)
    with pytest.raises(ValidationError):
        PlanStep(
            step_id="unsafe id",
            action="safe_fallback",
            description="invalid identifier",
            completion_criteria=["rejected"],
        )
