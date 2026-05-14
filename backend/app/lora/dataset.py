from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


LoraTaskType = Literal["query_normalization", "slot_extraction", "measurement_formatting"]
FORBIDDEN_FIELD_NAMES = {
    "api_key",
    "authorization",
    "password",
    "raw_rag_text",
    "rag_context",
    "source_document_text",
}


class LoraTrainingExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: str = Field(min_length=1)
    task_type: LoraTaskType
    instruction: str = Field(min_length=1)
    input_text: str = Field(min_length=1)
    output_text: str = Field(min_length=1)
    source: Literal["user_confirmed", "rule_generated", "synthetic"] = "rule_generated"
    safety_level: Literal["S0", "S1", "S2"] = "S1"
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_forbidden_training_payload(self) -> "LoraTrainingExample":
        self._reject_forbidden_names(set(self.metadata))
        self._reject_forbidden_text(self.instruction)
        self._reject_forbidden_text(self.input_text)
        self._reject_forbidden_text(self.output_text)
        return self

    def _reject_forbidden_names(self, names: set[str]) -> None:
        normalized = {name.strip().lower() for name in names}
        forbidden = sorted(normalized & FORBIDDEN_FIELD_NAMES)
        if forbidden:
            raise ValueError(f"forbidden LoRA training fields: {', '.join(forbidden)}")

    def _reject_forbidden_text(self, value: str) -> None:
        normalized = value.lower()
        for marker in FORBIDDEN_FIELD_NAMES:
            if marker in normalized:
                raise ValueError(f"forbidden LoRA training content marker: {marker}")
