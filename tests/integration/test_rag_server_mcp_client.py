from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient


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
