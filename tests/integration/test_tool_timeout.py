from __future__ import annotations

import asyncio

from backend.app.agent.tool_caller import ToolCaller


async def _slow_tool() -> dict[str, str]:
    await asyncio.sleep(0.05)
    return {"status": "late"}


async def _fast_tool() -> dict[str, str]:
    return {"status": "ok"}


def test_tool_caller_returns_timeout_without_fabricating_result() -> None:
    caller = ToolCaller()

    result = asyncio.run(
        caller.call_with_timeout(
            "livestock_rag_search",
            _slow_tool,
            timeout_seconds=0.001,
            timeout_error_code="RAG_TIMEOUT",
        )
    )

    assert result.status == "error"
    assert result.data == {}
    assert result.error is not None
    assert result.error.error_code == "RAG_TIMEOUT"


def test_tool_caller_wraps_successful_result() -> None:
    caller = ToolCaller()

    result = asyncio.run(caller.call_with_timeout("fast_tool", _fast_tool, timeout_seconds=1))

    assert result.status == "success"
    assert result.data == {"status": "ok"}
    assert result.error is None

