from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient


pytestmark = pytest.mark.rag_server


def _real_rag_settings() -> Settings:
    repo_path = os.getenv("RAG_SERVER_PATH")
    if not repo_path:
        pytest.skip("RAG_SERVER_PATH is required for real RAG-SERVER smoke tests")

    repo_root = Path(repo_path).expanduser().resolve()
    if not repo_root.exists():
        pytest.fail(f"RAG_SERVER_PATH does not exist: {repo_root}")

    python_executable = os.getenv("RAG_SERVER_PYTHON")
    if not python_executable:
        local_python = _python_from_run_local(repo_root)
        bundled_python = repo_root / ".venv" / "Scripts" / "python.exe"
        if local_python is not None:
            python_executable = str(local_python)
        else:
            python_executable = str(bundled_python if bundled_python.exists() else sys.executable)

    return Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_root),
            "python_executable": python_executable,
            "collection": os.getenv("RAG_SERVER_COLLECTION", "default"),
            "timeout_seconds": 30,
        }
    )


def _python_from_run_local(repo_root: Path) -> Path | None:
    script = repo_root / "scripts" / "run_local.ps1"
    if not script.exists():
        return None
    for line in script.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("$Python"):
            continue
        raw_path = line.split("=", 1)[1].strip().strip("\"'")
        candidate = Path(raw_path)
        if candidate.exists():
            return candidate
    return None


def test_real_rag_server_mcp_lists_tools_and_calls_collection_tool() -> None:
    settings = _real_rag_settings()
    client = RagServerMcpClient(settings)

    async def scenario() -> None:
        try:
            tools_result = await client._request("tools/list", {})
            tool_names = {item.get("name") for item in tools_result.get("tools", [])}
            assert "list_collections" in tool_names
            assert "query_knowledge_hub" in tool_names
            assert "get_document_summary" in tool_names

            result = await client._call_tool("list_collections", {"include_stats": False})
            payload = client._tool_result_payload(result)
            assert payload.get("isError") is not True
            assert payload
        finally:
            await client.close()

    asyncio.run(scenario())
