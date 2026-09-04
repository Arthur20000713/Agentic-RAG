from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

from backend.app.core.config import Settings
from backend.app.evaluation.real_rag_preflight import RealRagPreflightRunner


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / f"v4_preflight_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _make_mock_rag_server(
    root: Path,
    *,
    collections: list[str] | list[dict[str, object]] | None = None,
    collections_text: str | None = None,
) -> Path:
    server_dir = root / "src" / "mcp_server"
    config_dir = root / "config"
    server_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (server_dir / "__init__.py").write_text("", encoding="utf-8")
    (config_dir / "settings.yaml").write_text(
        "\n".join(
            [
                "llm:",
                "  provider: openai",
                "  api_key: secret-value",
                "embedding:",
                "  provider: local",
                "  model: local-hash-embedding",
                "vector_store:",
                "  collection_name: knowledge_hub",
                "",
            ]
        ),
        encoding="utf-8",
    )
    collections_json = json.dumps(collections or [], ensure_ascii=False)
    collections_text_literal = repr(collections_text)
    (server_dir / "server.py").write_text(
        dedent(
            f"""
            from __future__ import annotations

            import json
            import sys

            COLLECTIONS = {collections_json}
            COLLECTIONS_TEXT = {collections_text_literal}


            def send(payload: dict) -> None:
                sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\\n")
                sys.stdout.flush()


            for line in sys.stdin:
                message = json.loads(line)
                method = message.get("method")
                request_id = message.get("id")
                if method == "initialize":
                    send({{"jsonrpc": "2.0", "id": request_id, "result": {{"protocolVersion": "2024-11-05"}}}})
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/list":
                    send({{
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {{"tools": [{{"name": "query_knowledge_hub"}}, {{"name": "list_collections"}}]}},
                    }})
                elif method == "tools/call":
                    params = message.get("params") or {{}}
                    if params.get("name") == "list_collections":
                        payload = {{"text": COLLECTIONS_TEXT}} if COLLECTIONS_TEXT is not None else {{"collections": COLLECTIONS}}
                        send({{
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {{
                                "isError": False,
                                "content": [{{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}}],
                            }},
                        }})
                    else:
                        send({{"jsonrpc": "2.0", "id": request_id, "error": {{"code": -32602, "message": "bad tool"}}}})
            """
        ),
        encoding="utf-8",
    )
    return root.resolve()


def _make_mock_rag_server_with_direct_collections(root: Path) -> Path:
    repo_path = _make_mock_rag_server(root, collections_text="No collections found.")
    (repo_path / "src" / "mcp_server" / "protocol_handler.py").write_text(
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
                    return ToolResult(json.dumps({"collections": ["default"]}, ensure_ascii=False))


            def _register_default_tools(handler: ProtocolHandler) -> None:
                return None
            """
        ),
        encoding="utf-8",
    )
    return repo_path


def _write_source_manifest(root: Path, *, collection: str = "livestock_v4_1") -> Path:
    path = root / "source_manifest.yaml"
    path.write_text(
        f"""
version: 1
collection: {collection}
sources:
  - source_id: source_a
    title: Source A
    source_uri: https://example.com/a
    language: EN
    organization: Example
    topics: [calf_health]
    usage: [eval]
    ingestion_status: eval_only
    license_note: Link only.
  - source_id: source_b
    title: Source B
    source_uri: https://example.com/b
    language: ZH
    organization: Example
    topics: [biosecurity]
    usage: [knowledge_base]
    ingestion_status: approved_summary_only
    license_note: Summary only.
""",
        encoding="utf-8",
    )
    return path


def test_preflight_includes_manifest_summary_and_collection_warning() -> None:
    work_dir = _tmp_dir()
    repo_path = _make_mock_rag_server(work_dir / "mock_rag_server", collections=["default"])
    manifest_path = _write_source_manifest(work_dir, collection="livestock_v4_1")
    output_dir = work_dir / "reports"
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_path),
            "python_executable": sys.executable,
            "collection": "default",
            "timeout_seconds": 2,
        }
    )

    report = asyncio.run(
        RealRagPreflightRunner(settings, output_dir=output_dir, source_manifest_path=manifest_path).run()
    )
    payload = json.loads((output_dir / "real_rag_preflight.json").read_text(encoding="utf-8"))

    assert report.status == "passed"
    assert report.target_collection == "default"
    assert report.expected_collection == "livestock_v4_1"
    assert report.manifest_collection == "livestock_v4_1"
    assert report.manifest_source_count == 2
    assert "SOURCE_MANIFEST_COLLECTION_MISMATCH" in report.warnings
    assert payload["manifest_collection"] == "livestock_v4_1"
    assert payload["manifest_source_count"] == 2


def test_preflight_detects_collection_mismatch_and_writes_report() -> None:
    work_dir = _tmp_dir()
    repo_path = _make_mock_rag_server(work_dir / "mock_rag_server", collections=["knowledge_hub"])
    output_dir = work_dir / "reports"
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_path),
            "python_executable": sys.executable,
            "collection": "default",
            "timeout_seconds": 2,
        }
    )

    report = asyncio.run(RealRagPreflightRunner(settings, output_dir=output_dir).run())
    payload = json.loads((output_dir / "real_rag_preflight.json").read_text(encoding="utf-8"))

    assert report.status == "failed"
    assert report.error_code == "RAG_COLLECTION_NOT_FOUND"
    assert report.target_collection == "default"
    assert report.collections == ["knowledge_hub"]
    assert "query_knowledge_hub" in report.tools
    assert "RAG_COLLECTION_MISMATCH" in report.warnings
    assert payload["diagnostics"]["llm_api_key_present"] is True
    assert "secret-value" not in str(payload)


def test_preflight_treats_no_collections_text_as_empty_and_missing_target() -> None:
    work_dir = _tmp_dir()
    repo_path = _make_mock_rag_server(work_dir / "mock_rag_server", collections_text="No collections found.")
    output_dir = work_dir / "reports"
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_path),
            "python_executable": sys.executable,
            "collection": "default",
            "timeout_seconds": 2,
        }
    )

    report = asyncio.run(RealRagPreflightRunner(settings, output_dir=output_dir).run())

    assert report.status == "failed"
    assert report.collections == []
    assert report.error_code == "RAG_COLLECTION_NOT_FOUND"


def test_preflight_rejects_empty_collection_from_markdown_stats() -> None:
    work_dir = _tmp_dir()
    repo_path = _make_mock_rag_server(
        work_dir / "mock_rag_server",
        collections_text="1. **livestock_v4_2** - 0 documents",
    )
    output_dir = work_dir / "reports"
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_path),
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "timeout_seconds": 2,
        }
    )

    report = asyncio.run(RealRagPreflightRunner(settings, output_dir=output_dir).run())
    payload = json.loads((output_dir / "real_rag_preflight.json").read_text(encoding="utf-8"))

    assert report.status == "failed"
    assert report.error_code == "RAG_COLLECTION_EMPTY"
    assert report.target_document_count == 0
    assert payload["target_document_count"] == 0


def test_preflight_accepts_non_empty_collection_from_structured_stats() -> None:
    work_dir = _tmp_dir()
    repo_path = _make_mock_rag_server(
        work_dir / "mock_rag_server",
        collections=[{"name": "livestock_v4_2", "document_count": 18}],
    )
    output_dir = work_dir / "reports"
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_path),
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "timeout_seconds": 2,
        }
    )

    report = asyncio.run(RealRagPreflightRunner(settings, output_dir=output_dir).run())

    assert report.status == "passed"
    assert report.error_code is None
    assert report.collections == ["livestock_v4_2"]
    assert report.target_document_count == 18


def test_preflight_uses_direct_collection_fallback_when_stdio_returns_empty() -> None:
    work_dir = _tmp_dir()
    repo_path = _make_mock_rag_server_with_direct_collections(work_dir / "mock_rag_server")
    output_dir = work_dir / "reports"
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_path),
            "python_executable": sys.executable,
            "collection": "default",
            "timeout_seconds": 2,
        }
    )

    report = asyncio.run(RealRagPreflightRunner(settings, output_dir=output_dir).run())

    assert report.status == "passed"
    assert report.collections == ["default"]
    assert report.error_code is None
