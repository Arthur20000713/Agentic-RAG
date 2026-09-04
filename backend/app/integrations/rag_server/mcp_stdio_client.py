from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Awaitable

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.health import resolve_rag_server_path
from backend.app.integrations.rag_server.mapper import RagServerMapper
from backend.app.schemas.rag_server import RagDocumentSummary, RagSearchResult
from backend.app.services.trace_service import TraceService


class RagServerMcpError(RuntimeError):
    pass


class RagServerTimeoutPolicy:
    ERROR_CODE = "RAG_TIMEOUT"

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds

    async def wait_for(self, awaitable: Awaitable[Any], *, operation: str) -> Any:
        try:
            return await asyncio.wait_for(awaitable, timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise RagServerMcpError(
                f"{operation} timed out after {self.timeout_seconds:g}s"
            ) from exc

    @classmethod
    def is_timeout_error(cls, exc: RagServerMcpError) -> bool:
        return "timed out" in str(exc)


DIRECT_FALLBACK_WARNING = "RAG_DIRECT_FALLBACK_USED"
_JSON_FENCE_PATTERN = re.compile(r"```json\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
_RUNTIME_COPY_DIRS = ("src", "config", "data")
_RUNTIME_COPY_FILES = ("pyproject.toml", "main.py")


def parse_collection_names_from_text(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith("#"):
            continue
        lowered = cleaned.lower()
        if "available collections" in lowered:
            continue
        if lowered.startswith("no collection") or lowered.startswith("no collections"):
            continue
        if cleaned.startswith("没有") or cleaned.startswith("未找到"):
            continue
        match = re.match(r"^\d+\.\s+\*\*(?P<name>[^*]+)\*\*", cleaned)
        if match:
            names.append(match.group("name").strip())
            continue
        cleaned = cleaned.lstrip("-*").strip()
        if cleaned.startswith("**") and "**" in cleaned[2:]:
            names.append(cleaned.split("**", 2)[1].strip())
            continue
        names.append(cleaned.split()[0])
    return names


def parse_collection_stats_from_text(text: str) -> dict[str, int]:
    stats: dict[str, int] = {}
    pattern = re.compile(
        r"^\s*\d+\.\s+\*\*(?P<name>[^*]+)\*\*\s+-\s+"
        r"(?P<count>\d[\d,]*)\s+documents?\s*$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            stats[match.group("name").strip()] = int(match.group("count").replace(",", ""))
    return stats


def parse_document_summary_from_text(text: str, *, doc_id: str) -> dict[str, Any]:
    title_match = re.search(r"^## Document:\s*(.+)$", text, flags=re.MULTILINE)
    source_match = re.search(r"^\*\*Source:\*\*\s*(.+)$", text, flags=re.MULTILINE)
    chunks_match = re.search(r"^\*\*Chunks:\*\*\s*(\d+)$", text, flags=re.MULTILINE)
    tags_match = re.search(r"^\*\*Tags:\*\*\s*(.+)$", text, flags=re.MULTILINE)
    summary_match = re.search(
        r"^### Summary\s*$\s*(.*?)(?=^###\s|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if summary_match is None:
        return {"doc_id": doc_id, "summary": ""}

    tags: list[str] = []
    if tags_match:
        tags = [item.strip().strip("`") for item in tags_match.group(1).split(",") if item.strip()]
    return {
        "doc_id": doc_id,
        "title": title_match.group(1).strip() if title_match else None,
        "summary": summary_match.group(1).strip(),
        "tags": tags,
        "source": source_match.group(1).strip() if source_match else None,
        "chunk_count": int(chunks_match.group(1)) if chunks_match else None,
    }


class RagServerMcpClient(RagServerClient):
    def __init__(self, settings: Settings, trace_service: TraceService | None = None) -> None:
        self.settings = settings
        self.trace_service = trace_service
        self.process: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._repo_path: Path | None = None
        self._tool_lock = asyncio.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=100)
        self._stderr_thread: threading.Thread | None = None

    async def start(self) -> None:
        if self.process is not None:
            if self.process.poll() is None:
                return
            await self.close()

        repo_path = resolve_rag_server_path(self.settings)
        if repo_path is None:
            raise RagServerMcpError("RAG_SERVER_PATH or rag_server.repo_path is required")
        if not repo_path.exists():
            raise RagServerMcpError(f"RAG-SERVER path does not exist: {repo_path}")

        python_executable = self.settings.rag_server.python_executable or sys.executable
        run_repo_path = repo_path
        self._repo_path = run_repo_path
        self._stderr_lines.clear()
        self.process = subprocess.Popen(
            [
                python_executable,
                "-m",
                "src.mcp_server.server",
            ],
            cwd=str(run_repo_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=self._build_process_env(run_repo_path, source_repo_path=repo_path),
        )
        self._start_stderr_drain(self.process)
        try:
            await self._initialize()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        process = self.process
        stderr_thread = self._stderr_thread
        self.process = None
        self._stderr_thread = None
        if process is None:
            return

        if process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
        if stderr_thread is not None and stderr_thread.is_alive():
            await asyncio.to_thread(stderr_thread.join, 1)

    async def query(
        self,
        query: str,
        *,
        top_k: int = 4,
        collection: str | None = None,
        domain: str | None = None,
        species: str | None = None,
        request_id: str | None = None,
    ) -> RagSearchResult:
        started_at = time.perf_counter()
        resolved_collection = collection or self.settings.rag_server.collection
        attempt_count = 0
        result: dict[str, Any] | None = None
        arguments = {
            "query": query,
            "top_k": top_k,
            "collection": resolved_collection,
        }
        for attempt in range(1, 3):
            attempt_count = attempt
            try:
                result = await self._call_tool("query_knowledge_hub", arguments)
                break
            except RagServerMcpError as exc:
                error_code = self._error_code(exc)
                if error_code == RagServerTimeoutPolicy.ERROR_CODE and attempt == 1:
                    await self.close()
                    continue
                fallback_result = await self._try_direct_tool_fallback(
                    "query_knowledge_hub",
                    arguments,
                )
                if fallback_result is not None:
                    result = fallback_result
                    break
                error_result = RagSearchResult(
                    query=query,
                    status="error",
                    error_code=error_code,
                    error_message=str(exc),
                )
                error_result.raw_response_id = self._record_query_trace(
                    query=query,
                    collection=resolved_collection,
                    top_k=top_k,
                    status="error",
                    error_code=error_result.error_code,
                    result_count=0,
                    mapped_result_count=0,
                    request_id=request_id,
                    attempt_count=attempt_count,
                    latency_ms=self._elapsed_ms(started_at),
                )
                return error_result

        if result is None:
            error_result = RagSearchResult(
                query=query,
                status="error",
                error_code="RAG_MCP_ERROR",
                error_message="rag server query did not return a result",
            )
            error_result.raw_response_id = self._record_query_trace(
                query=query,
                collection=resolved_collection,
                top_k=top_k,
                status="error",
                error_code=error_result.error_code,
                result_count=0,
                mapped_result_count=0,
                request_id=request_id,
                attempt_count=attempt_count,
                latency_ms=self._elapsed_ms(started_at),
            )
            return error_result

        payload = self._tool_result_payload(result)
        if result.get("_direct_fallback_used"):
            self._append_mapping_warning(payload, DIRECT_FALLBACK_WARNING)
        if payload.get("isError") or payload.get("is_error"):
            fallback_result = await self._try_direct_tool_fallback(
                "query_knowledge_hub",
                arguments,
            )
            if fallback_result is not None:
                payload = self._tool_result_payload(fallback_result)
                self._append_mapping_warning(payload, DIRECT_FALLBACK_WARNING)
        if payload.get("isError") or payload.get("is_error"):
            error_result = RagSearchResult(
                query=query,
                status="error",
                error_code=payload.get("error_code", "RAG_INTERNAL_ERROR"),
                error_message=payload.get("error_message", "rag server tool returned an error"),
                raw_response_id=payload.get("raw_response_id"),
            )
            error_result.raw_response_id = self._record_query_trace(
                query=query,
                collection=resolved_collection,
                top_k=top_k,
                status="error",
                raw_response_id=error_result.raw_response_id,
                error_code=error_result.error_code,
                result_count=0,
                mapped_result_count=0,
                request_id=request_id,
                attempt_count=attempt_count,
                latency_ms=self._elapsed_ms(started_at),
            )
            return error_result
        mapped = RagServerMapper.to_search_result(
            payload,
            query=query,
            min_mapped_score=self.settings.rag_server.min_mapped_score,
            min_citation_count_for_answer=self.settings.rag_server.min_citation_count_for_answer,
            low_confidence_no_answer=self.settings.rag_server.low_confidence_no_answer,
        )
        mapped.raw_response_id = self._record_query_trace(
            query=query,
            collection=resolved_collection,
            top_k=top_k,
            status=mapped.status,
            raw_response_id=mapped.raw_response_id,
            result_count=len(payload.get("hits", payload.get("results", []))),
            mapped_result_count=len(mapped.hits),
            top_score=mapped.hits[0].score if mapped.hits else None,
            request_id=request_id,
            error_code=mapped.error_code,
            attempt_count=attempt_count,
            latency_ms=self._elapsed_ms(started_at),
        )
        return mapped

    async def get_document_summary(
        self,
        doc_id: str,
        *,
        collection: str | None = None,
    ) -> RagDocumentSummary:
        started_at = time.perf_counter()
        resolved_collection = collection or self.settings.rag_server.collection
        try:
            result = await self._call_tool(
                "get_document_summary",
                {
                    "doc_id": doc_id,
                    "collection": resolved_collection,
                },
            )
        except RagServerMcpError as exc:
            self._record_tool_trace(
                query=f"get_document_summary:{doc_id}",
                collection=resolved_collection,
                status="error",
                error_code=self._error_code(exc),
                latency_ms=self._elapsed_ms(started_at),
            )
            return RagDocumentSummary(doc_id=doc_id, summary=str(exc))

        payload = self._tool_result_payload(result)
        if isinstance(payload.get("text"), str):
            payload = parse_document_summary_from_text(payload["text"], doc_id=doc_id)
        summary = RagServerMapper.to_document_summary(payload, doc_id=doc_id)
        self._record_tool_trace(
            query=f"get_document_summary:{doc_id}",
            collection=resolved_collection,
            status="success",
            result_count=1,
            mapped_result_count=1,
            raw_response_id=payload.get("raw_response_id"),
            latency_ms=self._elapsed_ms(started_at),
        )
        return summary

    async def list_collections(self, *, include_stats: bool = True) -> list[str]:
        started_at = time.perf_counter()
        try:
            result = await self._call_tool(
                "list_collections",
                {"include_stats": include_stats},
            )
        except RagServerMcpError as exc:
            result = await self._try_direct_tool_fallback(
                "list_collections",
                {"include_stats": include_stats},
            )
            if result is None:
                self._record_tool_trace(
                    query="list_collections",
                    status="error",
                    error_code=self._error_code(exc),
                    latency_ms=self._elapsed_ms(started_at),
                )
                return []

        payload = self._tool_result_payload(result)
        collections = payload.get("collections")
        if isinstance(collections, list):
            names = [str(item) for item in collections]
            self._record_tool_trace(
                query="list_collections",
                status="success",
                result_count=len(names),
                mapped_result_count=len(names),
                raw_response_id=payload.get("raw_response_id"),
                latency_ms=self._elapsed_ms(started_at),
            )
            return names

        text = payload.get("text", "")
        if not text:
            names = []
        else:
            names = parse_collection_names_from_text(text)
        if not names and not result.get("_direct_fallback_used"):
            fallback_result = await self._try_direct_tool_fallback(
                "list_collections",
                {"include_stats": include_stats},
            )
            if fallback_result is not None:
                result = fallback_result
                payload = self._tool_result_payload(result)
                collections = payload.get("collections")
                if isinstance(collections, list):
                    names = [str(item) for item in collections]
                else:
                    names = parse_collection_names_from_text(payload.get("text", ""))
        self._record_tool_trace(
            query="list_collections",
            status="success" if names else "empty",
            result_count=len(names),
            mapped_result_count=len(names),
            raw_response_id=payload.get("raw_response_id"),
            latency_ms=self._elapsed_ms(started_at),
        )
        return names

    async def _initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "livestock-agentic-rag", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized", {})

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # A single stdio process has one shared stdout stream. Serializing tool
        # calls prevents concurrent readers from consuming each other's JSON-RPC
        # responses and then waiting forever for a response that was discarded.
        async with self._tool_lock:
            result = await self._request(
                "tools/call",
                {
                    "name": name,
                    "arguments": self._drop_none(arguments),
                },
            )
        if not isinstance(result, dict):
            raise RagServerMcpError("invalid MCP tool result")
        return result

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        await self._ensure_started()
        self._request_id += 1
        request_id = self._request_id
        try:
            await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            response = await self._read_response(request_id)
        except RagServerMcpError:
            await self.close()
            raise
        if "error" in response:
            error = response["error"]
            message = error.get("message", "mcp request failed") if isinstance(error, dict) else str(error)
            raise RagServerMcpError(message)
        return response.get("result")

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._ensure_started()
        try:
            await self._send({"jsonrpc": "2.0", "method": method, "params": params})
        except RagServerMcpError:
            await self.close()
            raise

    async def _ensure_started(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            await self.close()
        if self.process is None:
            await self.start()
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RagServerMcpError("MCP stdio process is not available")

    async def _send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RagServerMcpError("MCP stdio process is not available")
        stdin = self.process.stdin
        line = json.dumps(message, ensure_ascii=False) + "\n"

        def write_line() -> None:
            stdin.write(line)
            stdin.flush()

        try:
            await asyncio.to_thread(write_line)
        except (BrokenPipeError, OSError, ValueError) as exc:
            raise RagServerMcpError("MCP stdio process write failed") from exc

    async def _read_response(self, request_id: int) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise RagServerMcpError("MCP stdio process is not available")
        stdout = self.process.stdout

        timeout_policy = RagServerTimeoutPolicy(self.settings.rag_server.timeout_seconds)
        while True:
            raw_line = await timeout_policy.wait_for(
                asyncio.to_thread(stdout.readline),
                operation=f"MCP stdio response for request {request_id}",
            )
            if not raw_line:
                stderr_text = await self._read_stderr_tail()
                raise RagServerMcpError(f"MCP stdio process closed unexpectedly{stderr_text}")
            try:
                response = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if response.get("id") == request_id:
                return response

    async def _read_stderr_tail(self) -> str:
        raw = "".join(self._stderr_lines)[-4000:].strip()
        if not raw:
            return ""
        return f": {raw}"

    def _start_stderr_drain(self, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return

        def drain() -> None:
            for line in iter(process.stderr.readline, ""):
                self._stderr_lines.append(line)

        self._stderr_thread = threading.Thread(
            target=drain,
            name="rag-server-stderr-drain",
            daemon=True,
        )
        self._stderr_thread.start()

    def _tool_result_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result)
        content = payload.get("content")
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text = item.get("text", "")
                texts.append(text)
                parsed = self._parse_json_text(text)
                if isinstance(parsed, dict):
                    parsed.setdefault("isError", payload.get("isError", False))
                    return parsed
            references_payload = self._parse_references_payload(texts)
            if references_payload is not None:
                references_payload.setdefault("isError", payload.get("isError", False))
                return references_payload
            if texts:
                return {"text": texts[0], "isError": payload.get("isError", False)}
        return payload

    def _parse_json_text(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _parse_references_payload(self, texts: list[str]) -> dict[str, Any] | None:
        for text in texts:
            for match in _JSON_FENCE_PATTERN.finditer(text):
                parsed = self._parse_json_text(match.group(1).strip())
                if isinstance(parsed, dict) and ("citations" in parsed or "metadata" in parsed):
                    return self._references_to_payload(parsed, texts)
        return None

    def _references_to_payload(self, references: dict[str, Any], texts: list[str]) -> dict[str, Any]:
        metadata = references.get("metadata") if isinstance(references.get("metadata"), dict) else {}
        payload: dict[str, Any] = {
            "query": metadata.get("query"),
            "status": "success",
            "collection": metadata.get("collection"),
            "answer_text": self._answer_text_from_content(texts),
            "raw_response_id": metadata.get("response_id") or metadata.get("trace_id"),
            "hits": [],
            "citations": [],
        }
        for index, citation in enumerate(references.get("citations") or [], start=1):
            if not isinstance(citation, dict):
                continue
            source = citation.get("source") or citation.get("source_path") or citation.get("source_id")
            chunk_id = citation.get("chunk_id") or citation.get("id")
            title = citation.get("title") or self._title_from_source(source) or "Unknown source"
            citation_metadata = dict(citation.get("metadata") or {})
            if source:
                citation_metadata.setdefault("source", source)
                citation_metadata.setdefault("source_path", source)
            page = citation.get("page") or citation_metadata.get("page")
            section_title = citation.get("section_title") or citation_metadata.get("section_title")
            payload["hits"].append(
                {
                    "rank": citation.get("index") or index,
                    "chunk_id": chunk_id,
                    "document_id": source or citation.get("source_id") or chunk_id,
                    "document_title": title,
                    "content": citation.get("text_snippet") or citation.get("content") or "",
                    "page": page,
                    "section_title": section_title,
                    "score": citation.get("score", 0.0),
                    "metadata": citation_metadata,
                }
            )
            payload["citations"].append(
                {
                    "source_id": str(source or citation.get("source_id") or chunk_id),
                    "source_uri": citation.get("source_uri"),
                    "title": title,
                    "page": page,
                    "section_title": section_title,
                    "chunk_id": chunk_id,
                }
            )
        return payload

    def _answer_text_from_content(self, texts: list[str]) -> str | None:
        answer_parts = [text.strip() for text in texts if "References (JSON)" not in text]
        answer = "\n\n".join(part for part in answer_parts if part)
        return answer or None

    def _title_from_source(self, source: Any) -> str | None:
        if source in (None, ""):
            return None
        normalized = str(source).replace("\\", "/").rstrip("/")
        if not normalized:
            return None
        return normalized.rsplit("/", 1)[-1]

    async def _try_direct_tool_fallback(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        if os.getenv("RAG_SERVER_DISABLE_DIRECT_FALLBACK") == "1":
            return None
        try:
            result = await asyncio.to_thread(self._call_direct_tool, name, arguments)
        except RagServerMcpError:
            return None
        result["_direct_fallback_used"] = True
        return result

    def _call_direct_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        repo_path = resolve_rag_server_path(self.settings)
        if repo_path is None or not repo_path.exists():
            raise RagServerMcpError("RAG_SERVER_PATH or rag_server.repo_path is required")
        python_executable = self.settings.rag_server.python_executable or sys.executable
        completed = self._run_direct_tool_process(
            python_executable=python_executable,
            run_repo_path=repo_path,
            source_repo_path=repo_path,
            name=name,
            arguments=arguments,
        )
        if self._should_retry_in_runtime_copy(completed):
            runtime_repo_path = self._prepare_runtime_repo_copy(repo_path)
            completed = self._run_direct_tool_process(
                python_executable=python_executable,
                run_repo_path=runtime_repo_path,
                source_repo_path=repo_path,
                name=name,
                arguments=arguments,
            )
        if completed.returncode != 0:
            stderr_tail = (completed.stderr or "").strip()[-1000:]
            raise RagServerMcpError(f"direct RAG-SERVER tool call failed: {stderr_tail}")
        for line in reversed((completed.stdout or "").splitlines()):
            parsed = self._parse_json_text(line.strip())
            if isinstance(parsed, dict):
                return parsed
        raise RagServerMcpError("direct RAG-SERVER tool call returned invalid output")

    def _run_direct_tool_process(
        self,
        *,
        python_executable: str,
        run_repo_path: Path,
        source_repo_path: Path,
        name: str,
        arguments: dict[str, Any],
    ) -> subprocess.CompletedProcess[str]:
        script = """
from __future__ import annotations

import asyncio
import json
import sys

from src.mcp_server.protocol_handler import ProtocolHandler, _register_default_tools


def serialize_content(item):
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    if isinstance(item, dict):
        return item
    return {"type": "text", "text": str(item)}


async def main():
    payload = json.loads(sys.stdin.read() or "{}")
    handler = ProtocolHandler("agentic-rag-direct", "0.1")
    _register_default_tools(handler)
    result = await handler.execute_tool(payload["name"], payload.get("arguments") or {})
    output = {
        "isError": bool(getattr(result, "isError", False)),
        "content": [serialize_content(item) for item in getattr(result, "content", [])],
    }
    print(json.dumps(output, ensure_ascii=False))


asyncio.run(main())
"""
        return subprocess.run(
            [python_executable, "-c", script],
            cwd=str(run_repo_path),
            input=json.dumps({"name": name, "arguments": self._drop_none(arguments)}, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30.0, self.settings.rag_server.timeout_seconds),
            env=self._build_process_env(run_repo_path, source_repo_path=source_repo_path),
        )

    def _should_retry_in_runtime_copy(self, completed: subprocess.CompletedProcess[str]) -> bool:
        combined_output = f"{completed.stdout or ''}\n{completed.stderr or ''}".lower()
        return "readonly database" in combined_output or "permission denied" in combined_output

    def _prepare_runtime_repo_copy(self, repo_path: Path) -> Path:
        target = self._runtime_repo_copy_path(repo_path)
        runtime_root = target.parent
        target_resolved = target.resolve()
        runtime_root_resolved = runtime_root.resolve()
        if not target_resolved.is_relative_to(runtime_root_resolved):
            raise RagServerMcpError(f"unsafe runtime copy path: {target}")
        target.mkdir(parents=True, exist_ok=True)

        for dirname in _RUNTIME_COPY_DIRS:
            source = repo_path / dirname
            destination = target / dirname
            if not source.exists():
                continue
            if destination.exists():
                destination_resolved = destination.resolve()
                if not destination_resolved.is_relative_to(target_resolved):
                    raise RagServerMcpError(f"unsafe runtime copy destination: {destination}")
                shutil.rmtree(destination)
            shutil.copytree(
                source,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )

        for filename in _RUNTIME_COPY_FILES:
            source_file = repo_path / filename
            if source_file.exists():
                shutil.copy2(source_file, target / filename)
        (target / "logs").mkdir(exist_ok=True)
        return target

    def _runtime_repo_copy_path(self, repo_path: Path) -> Path:
        runtime_root = Path(
            os.getenv(
                "AGENTIC_RAG_SERVER_RUNTIME_ROOT",
                str(PROJECT_ROOT / ".tmp_tests" / "rag_server_runtime"),
            )
        )
        digest = hashlib.sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:12]
        return runtime_root / digest

    def _append_mapping_warning(self, payload: dict[str, Any], warning: str) -> None:
        warnings = payload.setdefault("mapping_warnings", [])
        if isinstance(warnings, list) and warning not in warnings:
            warnings.append(warning)

    def _error_code(self, exc: RagServerMcpError) -> str:
        message = str(exc)
        if "repo_path is required" in message or "RAG_SERVER_PATH" in message:
            return "RAG_SERVER_PATH_MISSING"
        if "timed out" in message:
            return RagServerTimeoutPolicy.ERROR_CODE
        return "RAG_MCP_ERROR"

    def _drop_none(self, data: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in data.items() if value is not None}

    def _build_process_env(self, repo_path: Path, *, source_repo_path: Path | None = None) -> dict[str, str]:
        env = os.environ.copy()
        source_repo_path = source_repo_path or repo_path
        pythonpath_parts = [
            path
            for path in [
                repo_path / ".deps",
                repo_path,
                source_repo_path / ".deps",
                source_repo_path,
                Path("C:/ProgramData/anaconda3/Lib/site-packages/win32"),
                Path("C:/ProgramData/anaconda3/Lib/site-packages/win32/lib"),
            ]
            if path.exists()
        ]
        if env.get("PYTHONPATH"):
            pythonpath_parts.append(Path(env["PYTHONPATH"]))
        if pythonpath_parts:
            env["PYTHONPATH"] = os.pathsep.join(str(path) for path in pythonpath_parts)

        path_parts = [
            path
            for path in [
                repo_path / ".deps" / "pywin32_system32",
                Path("C:/ProgramData/anaconda3/Library/bin"),
            ]
            if path.exists()
        ]
        if env.get("PATH"):
            path_parts.append(Path(env["PATH"]))
        if path_parts:
            env["PATH"] = os.pathsep.join(str(path) for path in path_parts)
        return env

    def _record_query_trace(
        self,
        *,
        query: str,
        collection: str | None,
        top_k: int | None,
        status: str,
        raw_response_id: str | None = None,
        result_count: int | None = None,
        mapped_result_count: int | None = None,
        top_score: float | None = None,
        error_code: str | None = None,
        request_id: str | None = None,
        attempt_count: int = 1,
        latency_ms: int | None = None,
    ) -> str | None:
        if self.trace_service is None:
            return raw_response_id
        return self.trace_service.record_rag_call(
            rag_mode=self.settings.rag_server.normalized_query_mode,
            request_id=request_id,
            collection=collection,
            query=query,
            top_k=top_k,
            result_count=result_count,
            mapped_result_count=mapped_result_count,
            top_score=top_score,
            raw_response_id=raw_response_id,
            status=status,
            error_code=error_code,
            attempt_count=attempt_count,
            latency_ms=latency_ms,
        )

    def _record_tool_trace(
        self,
        *,
        query: str,
        status: str,
        collection: str | None = None,
        raw_response_id: str | None = None,
        result_count: int | None = None,
        mapped_result_count: int | None = None,
        error_code: str | None = None,
        latency_ms: int | None = None,
    ) -> str | None:
        if self.trace_service is None:
            return raw_response_id
        return self.trace_service.record_rag_call(
            rag_mode=self.settings.rag_server.normalized_query_mode,
            collection=collection,
            query=query,
            raw_response_id=raw_response_id,
            result_count=result_count,
            mapped_result_count=mapped_result_count,
            status=status,
            error_code=error_code,
            latency_ms=latency_ms,
        )

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))
