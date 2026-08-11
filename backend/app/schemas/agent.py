from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


IntentType = Literal[
    "assistant_intro",
    "general_qa",
    "disease_consultation",
    "measurement_analysis",
    "out_of_scope",
]
RiskLevel = Literal["low", "medium", "high", "emergency"]


class RetrievedContext(BaseModel):
    chunk_id: str
    document_id: str | int | None = None
    title: str
    content: str
    page: int | None = None
    section_title: str | None = None
    score: float
    source_type: str | None = None


class AgentToolError(BaseModel):
    tool_name: str
    error_code: str
    message: str
