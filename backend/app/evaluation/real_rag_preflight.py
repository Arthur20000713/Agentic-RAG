from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.evaluation.source_manifest import (
    load_source_manifest,
    validate_source_manifest,
)
from backend.app.integrations.rag_server.diagnostics import (
    RagServerDiagnostics,
    build_rag_server_diagnostics,
)
from backend.app.integrations.rag_server.mcp_stdio_client import (
    RagServerMcpClient,
    RagServerMcpError,
    parse_collection_names_from_text,
    parse_collection_stats_from_text,
)


class RealRagPreflightReport(BaseModel):
    mode: str = "real"
    status: str
    target_collection: str
    expected_collection: str | None = None
    manifest_collection: str | None = None
    manifest_source_count: int = 0
    tools: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    target_document_count: int | None = None
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
        source_manifest_path: str | Path | None = None,
    ) -> None:
        self.settings = settings
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir
        self.client = client
        self.source_manifest_path = (
            Path(source_manifest_path)
            if source_manifest_path is not None
            else PROJECT_ROOT / "docs" / "rag_corpus" / "source_manifest.yaml"
        )
        if not self.source_manifest_path.is_absolute():
            self.source_manifest_path = PROJECT_ROOT / self.source_manifest_path

    async def run(self) -> RealRagPreflightReport:
        started_at = time.perf_counter()
        diagnostics = build_rag_server_diagnostics(self.settings)
        target_collection = self.settings.rag_server.collection
        manifest_context = self._manifest_context(target_collection)
        warnings = [*diagnostics.warnings, *manifest_context["warnings"]]
        if not diagnostics.repo_path_configured:
            return self._write_report(
                RealRagPreflightReport(
                    status="failed",
                    target_collection=target_collection,
                    expected_collection=manifest_context["expected_collection"],
                    manifest_collection=manifest_context["manifest_collection"],
                    manifest_source_count=manifest_context["manifest_source_count"],
                    error_code="RAG_SERVER_PATH_MISSING",
                    error_message="RAG_SERVER_PATH or rag_server.repo_path is required",
                    diagnostics=diagnostics,
                    warnings=warnings,
                    duration_ms=self._elapsed_ms(started_at),
                )
            )
        if not diagnostics.repo_path_exists:
            return self._write_report(
                RealRagPreflightReport(
                    status="failed",
                    target_collection=target_collection,
                    expected_collection=manifest_context["expected_collection"],
                    manifest_collection=manifest_context["manifest_collection"],
                    manifest_source_count=manifest_context["manifest_source_count"],
                    error_code="RAG_SERVER_PATH_NOT_FOUND",
                    error_message=f"RAG-SERVER path does not exist: {diagnostics.repo_path}",
                    diagnostics=diagnostics,
                    warnings=warnings,
                    duration_ms=self._elapsed_ms(started_at),
                )
            )

        client = self.client or RagServerMcpClient(self.settings)
        try:
            tools = await self._list_tools(client)
            collections, collection_counts = await self._list_collections(client)
            target_document_count = collection_counts.get(target_collection)
            error_code = self._collection_error(
                target_collection,
                collections,
                target_document_count,
            )
            return self._write_report(
                RealRagPreflightReport(
                    status="failed" if error_code else "passed",
                    target_collection=target_collection,
                    expected_collection=manifest_context["expected_collection"],
                    manifest_collection=manifest_context["manifest_collection"],
                    manifest_source_count=manifest_context["manifest_source_count"],
                    tools=tools,
                    collections=collections,
                    target_document_count=target_document_count,
                    error_code=error_code,
                    error_message=(
                        f"target collection not found: {target_collection}"
                        if error_code == "RAG_COLLECTION_NOT_FOUND"
                        else f"target collection is empty: {target_collection}"
                        if error_code == "RAG_COLLECTION_EMPTY"
                        else None
                    ),
                    diagnostics=diagnostics,
                    warnings=warnings,
                    duration_ms=self._elapsed_ms(started_at),
                )
            )
        except RagServerMcpError as exc:
            return self._write_report(
                RealRagPreflightReport(
                    status="failed",
                    target_collection=target_collection,
                    expected_collection=manifest_context["expected_collection"],
                    manifest_collection=manifest_context["manifest_collection"],
                    manifest_source_count=manifest_context["manifest_source_count"],
                    error_code=client._error_code(exc),
                    error_message=str(exc),
                    diagnostics=diagnostics,
                    warnings=warnings,
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

    async def _list_collections(self, client: RagServerMcpClient) -> tuple[list[str], dict[str, int]]:
        result = await client._call_tool("list_collections", {"include_stats": True})
        payload = client._tool_result_payload(result)
        collections = payload.get("collections")
        if isinstance(collections, list):
            names, counts = self._structured_collection_stats(collections)
            if names:
                return names, counts
        text = payload.get("text")
        names = parse_collection_names_from_text(text) if isinstance(text, str) else []
        if names:
            return names, parse_collection_stats_from_text(text)
        return await client.list_collections(include_stats=True), {}

    def _structured_collection_stats(
        self,
        collections: list[Any],
    ) -> tuple[list[str], dict[str, int]]:
        names: list[str] = []
        counts: dict[str, int] = {}
        for item in collections:
            if isinstance(item, dict):
                name_value = item.get("name") or item.get("collection") or item.get("collection_name")
                if not name_value:
                    continue
                name = str(name_value)
                count_value = item.get("document_count")
                if count_value is None:
                    count_value = item.get("count")
                if isinstance(count_value, int) and not isinstance(count_value, bool) and count_value >= 0:
                    counts[name] = count_value
            else:
                name = str(item)
            names.append(name)
        return names, counts

    def _collection_error(
        self,
        target_collection: str,
        collections: list[str],
        target_document_count: int | None,
    ) -> str | None:
        if target_collection not in collections:
            return "RAG_COLLECTION_NOT_FOUND"
        if target_document_count == 0:
            return "RAG_COLLECTION_EMPTY"
        return None

    def _manifest_context(self, target_collection: str) -> dict[str, Any]:
        if not self.source_manifest_path.exists():
            return {
                "expected_collection": None,
                "manifest_collection": None,
                "manifest_source_count": 0,
                "warnings": [],
            }
        try:
            manifest = load_source_manifest(self.source_manifest_path)
            validation_failures = validate_source_manifest(manifest)
        except (OSError, ValueError) as exc:
            return {
                "expected_collection": None,
                "manifest_collection": None,
                "manifest_source_count": 0,
                "warnings": [f"SOURCE_MANIFEST_INVALID: {exc}"],
            }
        warnings = [f"SOURCE_MANIFEST_INVALID: {failure}" for failure in validation_failures]
        manifest_collection = manifest.collection
        if manifest_collection and manifest_collection != target_collection:
            warnings.append("SOURCE_MANIFEST_COLLECTION_MISMATCH")
        return {
            "expected_collection": manifest_collection,
            "manifest_collection": manifest_collection,
            "manifest_source_count": len(manifest.sources),
            "warnings": warnings,
        }

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
