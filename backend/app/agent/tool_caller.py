from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from typing import Any

from backend.app.db.repositories import ToolCallLogRepository
from backend.app.schemas.mcp import ToolResult


class ToolCaller:
    def __init__(self, log_repository: ToolCallLogRepository | None = None) -> None:
        self.log_repository = log_repository

    async def call_with_timeout(
        self,
        tool_name: str,
        func: Callable[..., Any],
        *,
        timeout_seconds: float,
        timeout_error_code: str = "TOOL_TIMEOUT",
        session_id: str | None = None,
        input_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        started = time.perf_counter()
        try:
            raw_result = await asyncio.wait_for(
                self._call(func, **kwargs),
                timeout=timeout_seconds,
            )
            latency_ms = self._latency_ms(started)
            result = self._normalize_result(tool_name, raw_result, latency_ms=latency_ms)
            self._log(session_id, tool_name, input_data or kwargs, result)
            return result
        except asyncio.TimeoutError:
            latency_ms = self._latency_ms(started)
            result = ToolResult.failure(
                tool_name,
                timeout_error_code,
                "tool call timeout",
                latency_ms=latency_ms,
            )
            self._log(session_id, tool_name, input_data or kwargs, result)
            return result
        except Exception as exc:
            latency_ms = self._latency_ms(started)
            result = ToolResult.failure(
                tool_name,
                "TOOL_CALL_FAILED",
                str(exc),
                latency_ms=latency_ms,
            )
            self._log(session_id, tool_name, input_data or kwargs, result)
            return result

    async def _call(self, func: Callable[..., Any], **kwargs: Any) -> Any:
        value = func(**kwargs)
        if inspect.isawaitable(value):
            return await value
        return value

    def _normalize_result(
        self,
        tool_name: str,
        raw_result: Any,
        *,
        latency_ms: int,
    ) -> ToolResult:
        if isinstance(raw_result, ToolResult):
            raw_result.latency_ms = raw_result.latency_ms or latency_ms
            return raw_result
        if isinstance(raw_result, dict):
            return ToolResult.success(tool_name, raw_result, latency_ms=latency_ms)
        return ToolResult.success(tool_name, {"result": raw_result}, latency_ms=latency_ms)

    def _log(
        self,
        session_id: str | None,
        tool_name: str,
        input_data: dict[str, Any],
        result: ToolResult,
    ) -> None:
        if self.log_repository is None:
            return
        self.log_repository.add(
            session_id=session_id,
            tool_name=tool_name,
            input_data=input_data,
            output_data=result.data,
            status=result.status,
            error_code=None if result.error is None else result.error.error_code,
            error_message=None if result.error is None else result.error.message,
            latency_ms=result.latency_ms,
        )

    def _latency_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

