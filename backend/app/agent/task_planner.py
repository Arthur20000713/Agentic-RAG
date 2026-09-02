from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from pydantic import ValidationError

from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.livestock_triage import takeover_triage_context
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest
from backend.app.schemas.planning import PlanStep, TaskPlan


PLANNED_INTENTS = {"general_qa", "disease_consultation"}
_PLAN_FIELDS = {"plan_id", "goal", "steps", "completion_criteria", "source", "revision"}
_MODEL_METADATA_FIELDS = {
    "status",
    "schema_name",
    "fallback_required",
    "reason",
    "error_code",
    "provider",
    "model",
    "latency_ms",
}


@dataclass(frozen=True)
class PlanningOutcome:
    plan: TaskPlan
    fallback_used: bool
    fallback_reason: str | None = None


class TaskPlanner:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        primary_llm_client: Any | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    async def plan(self, state: MultiAgentState) -> PlanningOutcome:
        if state.intent not in PLANNED_INTENTS:
            raise ValueError(f"intent does not require planning: {state.intent}")

        if not self.settings.primary_llm.enabled:
            return self._fallback(state, "primary_llm_disabled")

        try:
            raw = await self.primary_llm_client.generate_json(self._request(state))
        except Exception as exc:
            return self._fallback(state, f"planner_error:{exc.__class__.__name__}")

        if raw.get("status") == "error" or raw.get("fallback_required") is True:
            reason = str(raw.get("error_code") or raw.get("reason") or "model_requested_fallback")
            return self._fallback(state, reason)

        payload = self._model_payload(raw, state)
        if payload is None:
            return self._fallback(state, "schema_validation_failed")
        try:
            plan = TaskPlan.model_validate(payload)
        except ValidationError:
            return self._fallback(state, "schema_validation_failed")
        if not self._supports_intent_shape(plan, state.intent):
            return self._fallback(state, "unsupported_plan_shape")
        return PlanningOutcome(plan=plan, fallback_used=False)

    def _model_payload(self, raw: dict[str, Any], state: MultiAgentState) -> dict[str, Any] | None:
        nested = raw.get("task_plan")
        if nested is not None:
            if not isinstance(nested, dict):
                return None
            if set(raw).difference({"task_plan", *_MODEL_METADATA_FIELDS}):
                return None
            payload = dict(nested)
        else:
            if set(raw).difference(_PLAN_FIELDS | _MODEL_METADATA_FIELDS):
                return None
            payload = {key: value for key, value in raw.items() if key in _PLAN_FIELDS}
        payload.update(
            {
                "plan_id": self._plan_id(state),
                "source": "model",
                "revision": 1,
            }
        )
        return payload

    def _fallback(self, state: MultiAgentState, reason: str) -> PlanningOutcome:
        return PlanningOutcome(
            plan=self._fallback_plan(state),
            fallback_used=True,
            fallback_reason=reason,
        )

    def _fallback_plan(self, state: MultiAgentState) -> TaskPlan:
        steps: list[PlanStep] = []
        retrieval_dependencies: list[str] = []
        query_source = "normalized_query"
        if state.intent == "disease_consultation":
            steps.append(
                PlanStep(
                    step_id="understand",
                    action="understand_disease",
                    description="Extract user-confirmed disease case facts.",
                    completion_criteria=["disease assessment is recorded"],
                )
            )
            retrieval_dependencies = ["understand"]
            query_source = "rag_query"

        steps.extend(
            [
                PlanStep(
                    step_id="retrieve",
                    action="query_knowledge_hub",
                    description="Retrieve evidence from the livestock knowledge hub.",
                    depends_on=retrieval_dependencies,
                    arguments={"query_source": query_source, "top_k": 4},
                    completion_criteria=["retrieval status is recorded"],
                ),
                PlanStep(
                    step_id="compose",
                    action="compose_grounded_answer",
                    description="Compose an answer constrained by retrieved evidence.",
                    depends_on=["retrieve"],
                    completion_criteria=["draft answer is recorded"],
                ),
            ]
        )
        return TaskPlan(
            plan_id=self._plan_id(state),
            goal="Answer the livestock question with verified evidence and safe limits.",
            steps=steps,
            completion_criteria=["answer is ready for final verification"],
            source="fallback",
            revision=1,
        )

    def _supports_intent_shape(self, plan: TaskPlan, intent: str) -> bool:
        actions = [step.action for step in plan.steps]
        if intent == "general_qa":
            if actions != ["query_knowledge_hub", "compose_grounded_answer"]:
                return False
            return (
                plan.steps[0].depends_on == []
                and plan.steps[0].arguments.get("query_source") == "normalized_query"
                and plan.steps[1].depends_on == [plan.steps[0].step_id]
            )
        if intent == "disease_consultation":
            if actions != ["understand_disease", "query_knowledge_hub", "compose_grounded_answer"]:
                return False
            return (
                plan.steps[0].depends_on == []
                and plan.steps[1].depends_on == [plan.steps[0].step_id]
                and plan.steps[1].arguments.get("query_source") == "rag_query"
                and plan.steps[2].depends_on == [plan.steps[1].step_id]
            )
        return False

    def _plan_id(self, state: MultiAgentState) -> str:
        identity = f"{state.session_id}:{state.request_id or ''}:{state.user_query}"
        return f"plan_{sha256(identity.encode('utf-8')).hexdigest()[:16]}"

    def _request(self, state: MultiAgentState) -> PrimaryLLMRequest:
        context: dict[str, Any] = {
            "intent": state.intent,
            "normalized_query": state.normalized_query or state.user_query,
        }
        if triage_context := takeover_triage_context(state.livestock_triage):
            context["livestock_triage"] = triage_context
        return PrimaryLLMRequest(
            prompt=(
                "Create the smallest valid task plan for this livestock request. "
                "Do not rewrite or decompose the query and do not add a second retrieval."
            ),
            schema_name="task_plan",
            context=context,
            system_prompt=(
                "Return exactly one JSON task plan. Allowed actions are understand_disease, "
                "query_knowledge_hub, and compose_grounded_answer. A general_qa plan must contain "
                "retrieve then compose. A disease_consultation plan must contain understand, retrieve, "
                "then compose. Retrieval arguments must use query_source normalized_query for general_qa "
                "or rag_query for disease_consultation, plus top_k from 1 to 20. Do not include prompts, "
                "chain-of-thought, arbitrary tools, query rewrites, memory writes, or safety actions."
            ),
        )


__all__ = ["PLANNED_INTENTS", "PlanningOutcome", "TaskPlanner"]
