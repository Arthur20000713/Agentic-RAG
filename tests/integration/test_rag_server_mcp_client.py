from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import RagTraceRepository
from backend.app.integrations.rag_server.mcp_stdio_client import (
    RagServerMcpClient,
    RagServerMcpError,
    parse_collection_names_from_text,
    parse_document_summary_from_text,
)
from backend.app.services.trace_service import TraceService


def _make_mock_rag_server() -> Path:
    root = Path(".tmp_tests") / "mock_rag_server"
    server_dir = root / "src" / "mcp_server"
    server_dir.mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "server.py").write_text(
        dedent(
            """
            from __future__ import annotations

            import json
            import os
            import sys

            with open("cwd_marker.txt", "w", encoding="utf-8") as marker:
                marker.write(os.getcwd())


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
                            "serverInfo": {"name": "mock-rag-server", "version": "0.1"},
                        },
                    })
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/list":
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "tools": [
                                {"name": "query_knowledge_hub"},
                                {"name": "list_collections"},
                                {"name": "get_document_summary"},
                            ]
                        },
                    })
                elif method == "tools/call":
                    params = message.get("params") or {}
                    name = params.get("name")
                    args = params.get("arguments") or {}
                    if name == "query_knowledge_hub":
                        payload = {
                            "query": args.get("query"),
                            "status": "success",
                            "hits": [
                                {
                                    "chunk_id": "mock_chunk_1",
                                    "document_id": "mock_doc",
                                    "document_title": "Mock Cattle Manual",
                                    "content": "Mock calf diarrhea guidance.",
                                    "page": 7,
                                    "section_title": "Mock Section",
                                    "score": 0.91,
                                }
                            ],
                            "citations": [
                                {
                                    "source_id": "mock_doc",
                                    "title": "Mock Cattle Manual",
                                    "page": 7,
                                    "section_title": "Mock Section",
                                    "chunk_id": "mock_chunk_1",
                                }
                            ],
                        }
                    elif name == "list_collections":
                        payload = {"collections": ["default", "mock"], "cwd": os.getcwd()}
                    elif name == "get_document_summary":
                        payload = {
                            "doc_id": args.get("doc_id"),
                            "title": "Mock Cattle Manual",
                            "summary": "Mock summary text.",
                            "tags": ["mock"],
                            "source": "mock",
                            "chunk_count": 1,
                        }
                    else:
                        send({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "isError": True,
                                "content": [{"type": "text", "text": "unknown tool"}],
                            },
                        })
                        continue
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "isError": False,
                            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                        },
                    })
                else:
                    send({
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "method not found"},
                    })
            """
        ),
        encoding="utf-8",
    )
    return root.resolve()


def _settings(repo_path: Path) -> Settings:
    return Settings(
        rag_server={
            "query_mode": "mcp_stdio",
            "repo_path": str(repo_path),
            "python_executable": sys.executable,
            "collection": "default",
            "timeout_seconds": 2,
        }
    )


def test_parse_collection_names_handles_real_rag_server_markdown() -> None:
    text = """
    ## Available Collections (1 total)

    1. **default** - 1 documents
    """

    assert parse_collection_names_from_text(text) == ["default"]


def test_parse_document_summary_handles_real_rag_server_markdown() -> None:
    text = """
## Document: Raising dairy heifers from birth to weaning

**Document ID:** `chunk_1`
**Source:** uga_raising_dairy_heifers
**Chunks:** 1
**Tags:** `SUMMARY_ONLY`, `CALF`

### Summary

Weaning guidance emphasizes a stable transition, clean water, and written feeding records.

### Additional Metadata

- **topics:** calf_feeding,weaning
"""

    payload = parse_document_summary_from_text(text, doc_id="chunk_1")

    assert payload["title"] == "Raising dairy heifers from birth to weaning"
    assert payload["summary"].startswith("Weaning guidance")
    assert payload["tags"] == ["SUMMARY_ONLY", "CALF"]
    assert payload["source"] == "uga_raising_dairy_heifers"
    assert payload["chunk_count"] == 1


def test_tool_result_payload_parses_real_rag_server_references_json() -> None:
    client = RagServerMcpClient(Settings(rag_server={"query_mode": "mcp_stdio", "repo_path": None}))
    result = {
        "isError": False,
        "content": [
            {"type": "text", "text": "## Query Results\n\nSample Document answer."},
            {
                "type": "text",
                "text": dedent(
                    """
                    ---
                    **References (JSON):**
                    ```json
                    {
                      "citations": [
                        {
                          "chunk_id": "8ec60778_0000_fafadaee",
                          "source": "tests\\\\fixtures\\\\sample_documents\\\\simple.pdf",
                          "score": 0.0328,
                          "text_snippet": "This is a sample document for RAG testing.",
                          "metadata": {"page": 1}
                        }
                      ],
                      "metadata": {
                        "query": "Sample Document",
                        "collection": "default",
                        "result_count": 1
                      },
                      "has_images": false,
                      "image_count": 0
                    }
                    ```
                    """
                ),
            },
        ],
    }

    payload = client._tool_result_payload(result)

    assert payload["query"] == "Sample Document"
    assert payload["collection"] == "default"
    assert payload["answer_text"].startswith("## Query Results")
    assert payload["hits"][0]["chunk_id"] == "8ec60778_0000_fafadaee"
    assert payload["hits"][0]["document_title"] == "simple.pdf"
    assert payload["hits"][0]["content"] == "This is a sample document for RAG testing."
    assert payload["citations"][0]["title"] == "simple.pdf"


def test_mcp_client_lifecycle_starts_with_repo_cwd_and_closes() -> None:
    repo_path = _make_mock_rag_server()
    client = RagServerMcpClient(_settings(repo_path))

    async def scenario() -> None:
        await client.start()
        assert client.process is not None
        assert client.process.returncode is None

        collections = await client.list_collections()
        assert collections == ["default", "mock"]
        assert (repo_path / "cwd_marker.txt").read_text(encoding="utf-8") == str(repo_path)

        await client.close()
        assert client.process is None

    asyncio.run(scenario())


def test_mcp_client_ignores_stale_runtime_copy_during_normal_start() -> None:
    repo_path = _make_mock_rag_server()
    client = RagServerMcpClient(_settings(repo_path))
    runtime_path = client._prepare_runtime_repo_copy(repo_path)
    runtime_marker = runtime_path / "cwd_marker.txt"
    runtime_marker.unlink(missing_ok=True)

    async def scenario() -> None:
        await client.start()
        collections = await client.list_collections()
        await client.close()

        assert collections == ["default", "mock"]
        assert (repo_path / "cwd_marker.txt").read_text(encoding="utf-8") == str(repo_path)
        assert not runtime_marker.exists()

    asyncio.run(scenario())


def test_mcp_client_calls_query_and_summary_tools() -> None:
    repo_path = _make_mock_rag_server()
    client = RagServerMcpClient(_settings(repo_path))

    async def scenario() -> None:
        result = await client.query("犊牛腹泻怎么办", top_k=1, collection="default")
        summary = await client.get_document_summary("mock_doc", collection="default")
        await client.close()

        assert result.status == "success"
        assert result.hits[0].chunk_id == "mock_chunk_1"
        assert result.citations[0].title == "Mock Cattle Manual"
        assert summary.doc_id == "mock_doc"
        assert summary.summary == "Mock summary text."

    asyncio.run(scenario())


def test_mcp_client_serializes_concurrent_tool_calls(monkeypatch) -> None:
    client = RagServerMcpClient(Settings())
    active_calls = 0
    max_active_calls = 0

    async def fake_request(method: str, params: dict) -> dict:
        nonlocal active_calls, max_active_calls
        assert method == "tools/call"
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        await asyncio.sleep(0.02)
        active_calls -= 1
        return {"name": params["name"]}

    monkeypatch.setattr(client, "_request", fake_request)

    async def scenario() -> None:
        results = await asyncio.gather(
            client._call_tool("first", {}),
            client._call_tool("second", {}),
        )

        assert [result["name"] for result in results] == ["first", "second"]
        assert max_active_calls == 1

    asyncio.run(scenario())


def test_mcp_client_restarts_process_that_exited_without_cached_returncode(monkeypatch) -> None:
    client = RagServerMcpClient(Settings())

    class ExitedProcess:
        stdin = object()
        stdout = object()
        returncode = None

        @staticmethod
        def poll() -> int:
            return 7

    exited_process = ExitedProcess()
    client.process = exited_process  # type: ignore[assignment]
    closed = False
    started = False

    async def fake_close() -> None:
        nonlocal closed
        closed = True
        client.process = None

    async def fake_start() -> None:
        nonlocal started
        started = True
        client.process = ExitedProcess()  # type: ignore[assignment]

    monkeypatch.setattr(client, "close", fake_close)
    monkeypatch.setattr(client, "start", fake_start)

    asyncio.run(client._ensure_started())

    assert closed is True
    assert started is True


def test_mcp_client_maps_broken_pipe_and_closes_transport(monkeypatch) -> None:
    client = RagServerMcpClient(Settings())
    closed = False

    async def fake_ensure_started() -> None:
        return None

    async def broken_send(message: dict) -> None:  # noqa: ARG001
        raise RagServerMcpError("MCP stdio process write failed")

    async def fake_close() -> None:
        nonlocal closed
        closed = True

    monkeypatch.setattr(client, "_ensure_started", fake_ensure_started)
    monkeypatch.setattr(client, "_send", broken_send)
    monkeypatch.setattr(client, "close", fake_close)

    with pytest.raises(RagServerMcpError, match="write failed"):
        asyncio.run(client._request("tools/list", {}))

    assert closed is True


def test_mcp_client_missing_repo_path_returns_error_result(monkeypatch) -> None:
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    client = RagServerMcpClient(Settings(rag_server={"query_mode": "mcp_stdio", "repo_path": None}))

    result = asyncio.run(client.query("犊牛腹泻怎么办"))

    assert result.status == "error"
    assert result.error_code == "RAG_SERVER_PATH_MISSING"


@pytest.mark.rag_server
def test_real_rag_server_mcp_smoke_requires_env_path() -> None:
    repo_path = os.getenv("RAG_SERVER_PATH")
    if not repo_path:
        pytest.skip("RAG_SERVER_PATH is required for real RAG-SERVER MCP smoke tests")

    client = RagServerMcpClient(Settings(rag_server={"query_mode": "mcp_stdio", "repo_path": repo_path}))

    async def scenario() -> None:
        collections = await client.list_collections()
        await client.close()
        assert isinstance(collections, list)

    asyncio.run(scenario())


def test_mcp_client_records_query_trace() -> None:
    repo_path = _make_mock_rag_server()
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    traces = RagTraceRepository(conn)
    client = RagServerMcpClient(_settings(repo_path), trace_service=TraceService(traces))

    async def scenario() -> None:
        result = await client.query("calf diarrhea", top_k=1, collection="default")
        await client.close()

        stored = conn.execute(
            "SELECT * FROM rag_trace_log WHERE raw_response_id = ?",
            (result.raw_response_id,),
        ).fetchone()

        assert stored is not None
        assert stored["rag_mode"] == "real"
        assert stored["collection"] == "default"
        assert stored["query"] == "calf diarrhea"
        assert stored["top_k"] == 1
        assert stored["result_count"] == 1
        assert stored["mapped_result_count"] == 1
        assert stored["status"] == "success"
        assert stored["error_code"] is None

    asyncio.run(scenario())


def test_mcp_client_records_error_trace_for_missing_repo_path(monkeypatch) -> None:
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    traces = RagTraceRepository(conn)
    client = RagServerMcpClient(
        Settings(rag_server={"query_mode": "mcp_stdio", "repo_path": None}),
        trace_service=TraceService(traces),
    )

    result = asyncio.run(client.query("calf diarrhea", top_k=3, collection="default"))
    stored = conn.execute(
        "SELECT * FROM rag_trace_log WHERE raw_response_id = ?",
        (result.raw_response_id,),
    ).fetchone()

    assert result.status == "error"
    assert result.error_code == "RAG_SERVER_PATH_MISSING"
    assert stored is not None
    assert stored["rag_mode"] == "real"
    assert stored["collection"] == "default"
    assert stored["query"] == "calf diarrhea"
    assert stored["top_k"] == 3
    assert stored["status"] == "error"
    assert stored["error_code"] == "RAG_SERVER_PATH_MISSING"
