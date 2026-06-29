from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import RagTraceRepository
from backend.app.integrations.rag_server import create_rag_server_client
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient, RagServerTimeoutPolicy
from backend.app.services.trace_service import TraceService


def _make_slow_mock_rag_server() -> Path:
    root = Path(".tmp_tests") / f"slow_mock_rag_server_{uuid4().hex}"
    server_dir = root / "src" / "mcp_server"
    server_dir.mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "server.py").write_text(
        dedent(
            """
            from __future__ import annotations

            import json
            import sys
            import time


            def send(payload: dict) -> None:
                sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\\n")
                sys.stdout.flush()


            for line in sys.stdin:
                message = json.loads(line)
                method = message.get("method")
                request_id = message.get("id")
                if method == "initialize":
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                        },
                    })
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/call":
                    time.sleep(1)
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "isError": False,
                            "content": [{"type": "text", "text": "{\\"hits\\": []}"}],
                        },
                    })
            """
        ),
        encoding="utf-8",
    )
    return root.resolve()


def _make_timeout_once_mock_rag_server() -> Path:
    root = Path(".tmp_tests") / f"timeout_once_mock_rag_server_{uuid4().hex}"
    server_dir = root / "src" / "mcp_server"
    server_dir.mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "server.py").write_text(
        dedent(
            """
            from __future__ import annotations

            import json
            from pathlib import Path
            import sys
            import time

            COUNTER = Path("__COUNTER_PATH__")


            def send(payload: dict) -> None:
                sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\\n")
                sys.stdout.flush()


            for line in sys.stdin:
                message = json.loads(line)
                method = message.get("method")
                request_id = message.get("id")
                if method == "initialize":
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                        },
                    })
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/call":
                    attempts = int(COUNTER.read_text(encoding="utf-8")) if COUNTER.exists() else 0
                    COUNTER.write_text(str(attempts + 1), encoding="utf-8")
                    if attempts == 0:
                        time.sleep(1)
                        continue
                    payload = {
                        "query": "calf diarrhea",
                        "status": "success",
                        "hits": [
                            {
                                "chunk_id": "retry_chunk",
                                "document_id": "retry_doc",
                                "document_title": "Retry Manual",
                                "content": "Recovered after timeout.",
                                "score": 0.88,
                            }
                        ],
                    }
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "isError": False,
                            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                        },
                    })
            """
        ),
        encoding="utf-8",
    )
    server_file = server_dir / "server.py"
    counter_path = str((root / "query_attempts.txt").resolve()).replace("\\", "\\\\")
    server_file.write_text(
        server_file.read_text(encoding="utf-8").replace("__COUNTER_PATH__", counter_path),
        encoding="utf-8",
    )
    return root.resolve()


def _make_direct_fallback_mock_rag_server() -> Path:
    root = Path(".tmp_tests") / f"direct_fallback_mock_rag_server_{uuid4().hex}"
    server_dir = root / "src" / "mcp_server"
    server_dir.mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "server.py").write_text(
        dedent(
            """
            from __future__ import annotations

            import json
            import sys
            import time


            def send(payload: dict) -> None:
                sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\\n")
                sys.stdout.flush()


            for line in sys.stdin:
                message = json.loads(line)
                method = message.get("method")
                request_id = message.get("id")
                if method == "initialize":
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                        },
                    })
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/call":
                    time.sleep(1)
            """
        ),
        encoding="utf-8",
    )
    (server_dir / "protocol_handler.py").write_text(
        dedent(
            """
            from __future__ import annotations

            import json


            class TextContent:
                def __init__(self, text: str) -> None:
                    self.text = text

                def model_dump(self) -> dict:
                    return {"type": "text", "text": self.text}


            class ToolResult:
                def __init__(self, text: str) -> None:
                    self.isError = False
                    self.content = [TextContent(text)]


            class ProtocolHandler:
                def __init__(self, name: str, version: str) -> None:
                    self.name = name
                    self.version = version

                async def execute_tool(self, name: str, arguments: dict) -> ToolResult:
                    if name == "query_knowledge_hub":
                        payload = {
                            "query": arguments.get("query"),
                            "status": "success",
                            "collection": arguments.get("collection"),
                            "hits": [
                                {
                                    "chunk_id": "direct_chunk",
                                    "document_id": "direct_doc",
                                    "document_title": "Direct Manual",
                                    "content": "Direct fallback result.",
                                    "score": 0.77,
                                }
                            ],
                        }
                        return ToolResult(json.dumps(payload, ensure_ascii=False))
                    return ToolResult(json.dumps({"collections": ["default"]}, ensure_ascii=False))


            def _register_default_tools(handler: ProtocolHandler) -> None:
                return None
            """
        ),
        encoding="utf-8",
    )
    return root.resolve()


def _make_readonly_then_runtime_mock_rag_server() -> Path:
    root = Path(".tmp_tests") / f"readonly_runtime_mock_rag_server_{uuid4().hex}"
    server_dir = root / "src" / "mcp_server"
    server_dir.mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "protocol_handler.py").write_text(
        dedent(
            """
            from __future__ import annotations

            import json
            import os
            import sys


            class TextContent:
                def __init__(self, text: str) -> None:
                    self.text = text

                def model_dump(self) -> dict:
                    return {"type": "text", "text": self.text}


            class ToolResult:
                def __init__(self, text: str) -> None:
                    self.isError = False
                    self.content = [TextContent(text)]


            class ProtocolHandler:
                def __init__(self, name: str, version: str) -> None:
                    self.name = name
                    self.version = version

                async def execute_tool(self, name: str, arguments: dict) -> ToolResult:
                    if "rag_server_runtime" not in os.getcwd():
                        sys.stderr.write("attempt to write a readonly database\\n")
                        return ToolResult("No collections found in the knowledge base.")
                    return ToolResult(json.dumps({"collections": ["default"]}, ensure_ascii=False))


            def _register_default_tools(handler: ProtocolHandler) -> None:
                return None
            """
        ),
        encoding="utf-8",
    )
    return root.resolve()


def test_real_rag_adapter_is_created_with_trace_service() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    trace_service = TraceService(RagTraceRepository(conn))
    settings = Settings(rag_server={"query_mode": "real", "repo_path": "."})

    client = create_rag_server_client(settings, trace_service=trace_service)

    assert isinstance(client, RagServerMcpClient)
    assert client.trace_service is trace_service


def test_mcp_client_timeout_returns_empty_error_result_and_records_trace() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    traces = RagTraceRepository(conn)
    repo_path = _make_slow_mock_rag_server()
    client = RagServerMcpClient(
        Settings(
            rag_server={
                "query_mode": "real",
                "repo_path": str(repo_path),
                "python_executable": sys.executable,
                "collection": "default",
                "timeout_seconds": 0.05,
            }
        ),
        trace_service=TraceService(traces),
    )

    result = asyncio.run(client.query("calf diarrhea", top_k=2, collection="default"))
    stored = conn.execute(
        "SELECT * FROM rag_trace_log WHERE raw_response_id = ?",
        (result.raw_response_id,),
    ).fetchone()

    assert result.status == "error"
    assert result.error_code == RagServerTimeoutPolicy.ERROR_CODE
    assert result.hits == []
    assert result.citations == []
    assert stored is not None
    assert stored["rag_mode"] == "real"
    assert stored["collection"] == "default"
    assert stored["query"] == "calf diarrhea"
    assert stored["top_k"] == 2
    assert stored["result_count"] == 0
    assert stored["mapped_result_count"] == 0
    assert stored["status"] == "error"
    assert stored["error_code"] == RagServerTimeoutPolicy.ERROR_CODE
    assert stored["attempt_count"] == 2


def test_mcp_client_restarts_and_retries_once_after_timeout() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    traces = RagTraceRepository(conn)
    repo_path = _make_timeout_once_mock_rag_server()
    client = RagServerMcpClient(
        Settings(
            rag_server={
                "query_mode": "real",
                "repo_path": str(repo_path),
                "python_executable": sys.executable,
                "collection": "default",
                "timeout_seconds": 0.75,
            }
        ),
        trace_service=TraceService(traces),
    )

    result = asyncio.run(client.query("calf diarrhea", top_k=2, collection="default"))
    stored = conn.execute(
        "SELECT * FROM rag_trace_log WHERE raw_response_id = ?",
        (result.raw_response_id,),
    ).fetchone()

    assert result.status == "success"
    assert result.hits[0].chunk_id == "retry_chunk"
    assert stored is not None
    assert stored["status"] == "success"
    assert stored["attempt_count"] == 2
    assert (repo_path / "query_attempts.txt").read_text(encoding="utf-8") == "2"


def test_mcp_client_uses_direct_tool_fallback_after_stdio_timeout() -> None:
    repo_path = _make_direct_fallback_mock_rag_server()
    client = RagServerMcpClient(
        Settings(
            rag_server={
                "query_mode": "real",
                "repo_path": str(repo_path),
                "python_executable": sys.executable,
                "collection": "default",
                "timeout_seconds": 0.05,
            }
        )
    )

    result = asyncio.run(client.query("calf diarrhea", top_k=2, collection="default"))

    assert result.status == "success"
    assert result.hits[0].chunk_id == "direct_chunk"
    assert "RAG_DIRECT_FALLBACK_USED" in result.mapping_warnings


def test_direct_tool_retries_from_writable_runtime_copy_after_readonly_stderr() -> None:
    repo_path = _make_readonly_then_runtime_mock_rag_server()
    client = RagServerMcpClient(
        Settings(
            rag_server={
                "query_mode": "real",
                "repo_path": str(repo_path),
                "python_executable": sys.executable,
                "collection": "default",
                "timeout_seconds": 1,
            }
        )
    )

    raw = client._call_direct_tool("list_collections", {"include_stats": False})
    payload = client._tool_result_payload(raw)

    assert payload["collections"] == ["default"]
