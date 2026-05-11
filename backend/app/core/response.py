from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.app.core.errors import AppError, ErrorCode


def new_request_id() -> str:
    return f"req_{uuid4().hex}"


class ApiResponse(BaseModel):
    code: int = ErrorCode.SUCCESS
    message: str = "success"
    data: Any = Field(default_factory=dict)
    request_id: str = Field(default_factory=new_request_id)

    @classmethod
    def ok(cls, data: Any = None, request_id: str | None = None) -> "ApiResponse":
        return cls(
            code=ErrorCode.SUCCESS,
            message="success",
            data={} if data is None else data,
            request_id=request_id or new_request_id(),
        )

    @classmethod
    def fail(
        cls,
        code: ErrorCode,
        message: str,
        data: Any = None,
        request_id: str | None = None,
    ) -> "ApiResponse":
        return cls(
            code=code,
            message=message,
            data={} if data is None else data,
            request_id=request_id or new_request_id(),
        )

    @classmethod
    def from_error(cls, error: AppError, request_id: str | None = None) -> "ApiResponse":
        data = {} if error.detail is None else {"detail": error.detail}
        return cls.fail(error.code, error.message, data=data, request_id=request_id)

