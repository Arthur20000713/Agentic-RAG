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
