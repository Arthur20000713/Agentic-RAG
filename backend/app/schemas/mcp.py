from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ToolStatus = Literal["success", "error"]


class ToolError(BaseModel):
    tool_name: str
    error_code: str
    message: str


class ToolResult(BaseModel):
    tool_name: str
    status: ToolStatus
    data: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None
    latency_ms: int | None = None

    @classmethod
    def success(
        cls,
        tool_name: str,
        data: dict[str, Any] | None = None,
        *,
        latency_ms: int | None = None,
    ) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            status="success",
            data=data or {},
            latency_ms=latency_ms,
        )

    @classmethod
    def failure(
        cls,
        tool_name: str,
        error_code: str,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> "ToolResult":
        return cls(
            tool_name=tool_name,
            status="error",
            data=data or {},
            error=ToolError(tool_name=tool_name, error_code=error_code, message=message),
            latency_ms=latency_ms,
        )

