from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.health import resolve_rag_server_path
from backend.app.integrations.rag_server.mapper import RagServerMapper
from backend.app.schemas.rag_server import RagDocumentSummary, RagSearchResult
from backend.app.services.trace_service import TraceService


class RagServerMcpError(RuntimeError):
    pass


class RagServerMcpClient(RagServerClient):
    def __init__(self, settings: Settings, trace_service: TraceService | None = None) -> None:
        self.settings = settings
        self.trace_service = trace_service
        self.process: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._repo_path: Path | None = None

    async def start(self) -> None:
        if self.process is not None and self.process.returncode is None:
            return

        repo_path = resolve_rag_server_path(self.settings)
        if repo_path is None:
            raise RagServerMcpError("RAG_SERVER_PATH or rag_server.repo_path is required")
        if not repo_path.exists():
            raise RagServerMcpError(f"RAG-SERVER path does not exist: {repo_path}")

        python_executable = self.settings.rag_server.python_executable or sys.executable
        self._repo_path = repo_path
        self.process = subprocess.Popen(
            [
                python_executable,
                "-m",
                "src.mcp_server.server",
            ],
            cwd=str(repo_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        await self._initialize()

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.returncode is not None:
            return

        process.terminate()
        try:
            await asyncio.to_thread(process.wait, timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait)

    async def query(
        self,
        query: str,
        *,
        top_k: int = 4,
        collection: str | None = None,
        domain: str | None = None,
        species: str | None = None,
    ) -> RagSearchResult:
        started_at = time.perf_counter()
        resolved_collection = collection or self.settings.rag_server.collection
        try:
            result = await self._call_tool(
                "query_knowledge_hub",
                {
                    "query": query,
                    "top_k": top_k,
                    "collection": resolved_collection,
                },
            )
        except RagServerMcpError as exc:
            error_result = RagSearchResult(
                query=query,
                status="error",
                error_code=self._error_code(exc),
                error_message=str(exc),
            )
            error_result.raw_response_id = self._record_query_trace(
                query=query,
                collection=resolved_collection,
                top_k=top_k,
                status="error",
                error_code=error_result.error_code,
                latency_ms=self._elapsed_ms(started_at),
            )
            return error_result

        payload = self._tool_result_payload(result)
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
                latency_ms=self._elapsed_ms(started_at),
            )
            return error_result
        mapped = RagServerMapper.to_search_result(payload, query=query)
        mapped.raw_response_id = self._record_query_trace(
            query=query,
            collection=resolved_collection,
            top_k=top_k,
            status=mapped.status,
            raw_response_id=mapped.raw_response_id,
            result_count=len(payload.get("hits", payload.get("results", []))),
            mapped_result_count=len(mapped.hits),
            top_score=mapped.hits[0].score if mapped.hits else None,
            error_code=mapped.error_code,
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
            self._record_tool_trace(
                query="list_collections",
                status="empty",
                result_count=0,
                mapped_result_count=0,
                raw_response_id=payload.get("raw_response_id"),
                latency_ms=self._elapsed_ms(started_at),
            )
            return []
        names: list[str] = []
        for line in text.splitlines():
            cleaned = line.strip().lstrip("-*").strip()
            if cleaned:
                names.append(cleaned.split()[0])
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
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response = await self._read_response(request_id)
        if "error" in response:
            error = response["error"]
            message = error.get("message", "mcp request failed") if isinstance(error, dict) else str(error)
            raise RagServerMcpError(message)
        return response.get("result")

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._ensure_started()
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _ensure_started(self) -> None:
        if self.process is None or self.process.returncode is not None:
            await self.start()
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RagServerMcpError("MCP stdio process is not available")

    async def _send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RagServerMcpError("MCP stdio process is not available")
        line = json.dumps(message, ensure_ascii=False) + "\n"

        def write_line() -> None:
            assert self.process is not None
            assert self.process.stdin is not None
            self.process.stdin.write(line)
            self.process.stdin.flush()

        await asyncio.to_thread(write_line)

    async def _read_response(self, request_id: int) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise RagServerMcpError("MCP stdio process is not available")

        timeout = self.settings.rag_server.timeout_seconds
        while True:
            raw_line = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=timeout,
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
        if self.process is None or self.process.stderr is None:
            return ""
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self.process.stderr.read, 4000),
                timeout=0.1,
            )
        except asyncio.TimeoutError:
            return ""
        if not raw:
            return ""
        return f": {raw.strip()}"

    def _tool_result_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result)
        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text = item.get("text", "")
                parsed = self._parse_json_text(text)
                if isinstance(parsed, dict):
                    parsed.setdefault("isError", payload.get("isError", False))
                    return parsed
                return {"text": text, "isError": payload.get("isError", False)}
        return payload

    def _parse_json_text(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _error_code(self, exc: RagServerMcpError) -> str:
        message = str(exc)
        if "repo_path is required" in message or "RAG_SERVER_PATH" in message:
            return "RAG_SERVER_PATH_MISSING"
        if "timed out" in message:
            return "RAG_TIMEOUT"
        return "RAG_MCP_ERROR"

    def _drop_none(self, data: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in data.items() if value is not None}

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
        latency_ms: int | None = None,
    ) -> str | None:
        if self.trace_service is None:
            return raw_response_id
        return self.trace_service.record_rag_call(
            rag_mode=self.settings.rag_server.normalized_query_mode,
            collection=collection,
            query=query,
            top_k=top_k,
            result_count=result_count,
            mapped_result_count=mapped_result_count,
            top_score=top_score,
            raw_response_id=raw_response_id,
            status=status,
            error_code=error_code,
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
