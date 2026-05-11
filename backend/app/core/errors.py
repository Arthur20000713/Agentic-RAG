from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    SUCCESS = 0
    INVALID_REQUEST = 40001
    NOT_FOUND = 40004
    UNAUTHORIZED = 40100
    FORBIDDEN = 40300
    LLM_FAILED = 50001
    RAG_SERVER_UNAVAILABLE = 50002
    TOOL_CALL_FAILED = 50003
    RAG_INGESTION_FAILED = 50004
    SAFETY_CHECK_FAILED = 50005


class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str, detail: object | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

