from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.integrations.rag_server.diagnostics import RagServerDiagnostics, build_rag_server_diagnostics
from backend.app.integrations.rag_server.mcp_stdio_client import (
    RagServerMcpClient,
    RagServerMcpError,
    parse_collection_names_from_text,
)


class RealRagPreflightReport(BaseModel):
    mode: str = "real"
    status: str
    target_collection: str
    tools: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    diagnostics: RagServerDiagnostics
    warnings: list[str] = Field(default_factory=list)


class RealRagPreflightRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        output_dir: str | Path | None = None,
        client: RagServerMcpClient | None = None,
    ) -> None:
        self.settings = settings
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir
        self.client = client

    async def run(self) -> RealRagPreflightReport:
        started_at = time.perf_counter()
        diagnostics = build_rag_server_diagnostics(self.settings)
        target_collection = self.settings.rag_server.collection
        if not diagnostics.repo_path_configured:
            return self._write_report(
                RealRagPreflightReport(
                    status="failed",
                    target_collection=target_collection,
                    error_code="RAG_SERVER_PATH_MISSING",
                    error_message="RAG_SERVER_PATH or rag_server.repo_path is required",
                    diagnostics=diagnostics,
                    warnings=diagnostics.warnings,
                    duration_ms=self._elapsed_ms(started_at),
                )
            )
        if not diagnostics.repo_path_exists:
            return self._write_report(
                RealRagPreflightReport(
                    status="failed",
                    target_collection=target_collection,
                    error_code="RAG_SERVER_PATH_NOT_FOUND",
                    error_message=f"RAG-SERVER path does not exist: {diagnostics.repo_path}",
                    diagnostics=diagnostics,
                    warnings=diagnostics.warnings,
                    duration_ms=self._elapsed_ms(started_at),
                )
            )

        client = self.client or RagServerMcpClient(self.settings)
        try:
            tools = await self._list_tools(client)
            collections = await self._list_collections(client)
            error_code = self._collection_error(target_collection, collections)
            return self._write_report(
                RealRagPreflightReport(
                    status="failed" if error_code else "passed",
                    target_collection=target_collection,
                    tools=tools,
                    collections=collections,
                    error_code=error_code,
                    error_message=(
                        f"target collection not found: {target_collection}"
                        if error_code == "RAG_COLLECTION_NOT_FOUND"
                        else None
                    ),
                    diagnostics=diagnostics,
                    warnings=diagnostics.warnings,
                    duration_ms=self._elapsed_ms(started_at),
                )
            )
        except RagServerMcpError as exc:
            return self._write_report(
                RealRagPreflightReport(
                    status="failed",
                    target_collection=target_collection,
                    error_code=client._error_code(exc),
                    error_message=str(exc),
                    diagnostics=diagnostics,
                    warnings=diagnostics.warnings,
                    duration_ms=self._elapsed_ms(started_at),
                )
            )
        finally:
            if self.client is None:
                close = getattr(client, "close", None)
                if close is not None:
                    await close()

    async def _list_tools(self, client: RagServerMcpClient) -> list[str]:
        result = await client._request("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else []
        names: list[str] = []
        for item in tools or []:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
        return names

    async def _list_collections(self, client: RagServerMcpClient) -> list[str]:
        result = await client._call_tool("list_collections", {"include_stats": False})
        payload = client._tool_result_payload(result)
        collections = payload.get("collections")
        if isinstance(collections, list):
            return [str(item) for item in collections]
        text = payload.get("text")
        if not isinstance(text, str):
            return []
        return parse_collection_names_from_text(text)

    def _collection_error(self, target_collection: str, collections: list[str]) -> str | None:
        if target_collection not in collections:
            return "RAG_COLLECTION_NOT_FOUND"
        return None

    def _write_report(self, report: RealRagPreflightReport) -> RealRagPreflightReport:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with (self.output_dir / "real_rag_preflight.json").open("w", encoding="utf-8") as file:
            json.dump(report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")
        return report

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))


def run_real_rag_preflight(settings: Settings, *, output_dir: str | Path | None = None) -> RealRagPreflightReport:
    return asyncio.run(RealRagPreflightRunner(settings, output_dir=output_dir).run())
