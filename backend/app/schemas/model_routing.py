from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from backend.app.schemas.agent import IntentType, RiskLevel

ModelName = Literal["primary", "local_small"]
ModelTaskType = Literal[
    "final_answer",
    "intent_routing",
    "query_normalization",
    "structured_extraction",
    "measurement_analysis",
    "summarization",
    "livestock_triage",
    "planning",
    "reasoning",
]
ModelRouteMode = Literal["disabled", "primary", "shadow", "takeover"]
ModelUsageSource = Literal["provider", "tokenizer", "estimate", "unavailable"]
ModelCallStatus = Literal["success", "fallback", "error"]
TriageScalar = StrictStr | StrictInt | StrictFloat | StrictBool


class TriageSlot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    value: TriageScalar
    source_span: str = Field(min_length=1, max_length=200)
    confidence: StrictFloat = Field(ge=0, le=1)


class LivestockTriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    intent_candidate: IntentType
    confidence: StrictFloat = Field(ge=0, le=1)
    slots: list[TriageSlot] = Field(default_factory=list, max_length=16)
    risk_candidate: RiskLevel
    risk_signals: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_unique_slots(self) -> LivestockTriageResult:
        names = [slot.name for slot in self.slots]
        if len(names) != len(set(names)):
            raise ValueError("slot names must be unique")
        return self


class ModelTokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    source: ModelUsageSource
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)
    total_tokens: StrictInt | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> ModelTokenUsage:
        counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        if self.source == "unavailable":
            if any(value is not None for value in counts):
                raise ValueError("unavailable usage cannot contain token counts")
            return self
        if any(value is None for value in counts):
            raise ValueError("measured or estimated usage requires all token counts")
        if self.total_tokens != self.input_tokens + self.output_tokens:  # type: ignore[operator]
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        return self


class ModelCostEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pricing_configured: StrictBool
    cost_scope: Literal["api_token_only"] = "api_token_only"
    input_usd_per_million_tokens: StrictFloat | None = Field(default=None, ge=0)
    output_usd_per_million_tokens: StrictFloat | None = Field(default=None, ge=0)
    input_cost_usd: StrictFloat | None = Field(default=None, ge=0)
    output_cost_usd: StrictFloat | None = Field(default=None, ge=0)
    total_cost_usd: StrictFloat | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_pricing(self) -> ModelCostEstimate:
        rates = (self.input_usd_per_million_tokens, self.output_usd_per_million_tokens)
        costs = (self.input_cost_usd, self.output_cost_usd, self.total_cost_usd)
        if not self.pricing_configured:
            if any(value is not None for value in (*rates, *costs)):
                raise ValueError("unconfigured pricing cannot contain costs or rates")
            return self
        if any(value is None for value in rates):
            raise ValueError("configured pricing requires input and output rates")
        if any(value is not None for value in costs) and any(value is None for value in costs):
            raise ValueError("cost values must be all present or all absent")
        if self.total_cost_usd is not None:
            expected = self.input_cost_usd + self.output_cost_usd  # type: ignore[operator]
            if abs(self.total_cost_usd - expected) > 1e-12:
                raise ValueError("total_cost_usd must equal input_cost_usd + output_cost_usd")
        return self


class ModelCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    operation_key: str = Field(min_length=1, max_length=256)
    task_type: ModelTaskType
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)
    selected_model: ModelName
    route_mode: ModelRouteMode
    status: ModelCallStatus
    fallback_reason: str | None = Field(default=None, max_length=160)
    latency_ms: StrictInt = Field(ge=0)
    usage: ModelTokenUsage
    cost: ModelCostEstimate

    @model_validator(mode="after")
    def validate_cost_matches_usage(self) -> ModelCallRecord:
        if self.usage.source == "unavailable" or not self.cost.pricing_configured:
            return self
        if self.cost.total_cost_usd is None:
            raise ValueError("measured usage with configured pricing requires costs")
        expected_input = self.usage.input_tokens * self.cost.input_usd_per_million_tokens / 1_000_000  # type: ignore[operator]
        expected_output = self.usage.output_tokens * self.cost.output_usd_per_million_tokens / 1_000_000  # type: ignore[operator]
        if (
            abs(self.cost.input_cost_usd - expected_input) > 1e-12  # type: ignore[operator]
            or abs(self.cost.output_cost_usd - expected_output) > 1e-12  # type: ignore[operator]
        ):
            raise ValueError("cost values must match token usage and pricing")
        return self


__all__ = [
    "LivestockTriageResult",
    "ModelCallRecord",
    "ModelCallStatus",
    "ModelCostEstimate",
    "ModelName",
    "ModelRouteMode",
    "ModelTaskType",
    "ModelTokenUsage",
    "ModelUsageSource",
    "TriageScalar",
    "TriageSlot",
]
