from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.health import resolve_rag_server_path


@dataclass(frozen=True)
class IngestResult:
    status: str
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error_code: str | None = None
    error_message: str | None = None


class RagServerCliGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ingest(
        self,
        path: str | Path,
        *,
        collection: str | None = None,
        dry_run: bool = False,
        timeout_seconds: float | None = None,
    ) -> IngestResult:
        repo_path = resolve_rag_server_path(self.settings)
        if repo_path is None:
            return IngestResult(
                status="failed",
                error_code="RAG_SERVER_PATH_MISSING",
                error_message="RAG_SERVER_PATH or rag_server.repo_path is required",
            )

        ingest_script = repo_path / "scripts" / "ingest.py"
        if not ingest_script.exists():
            return IngestResult(
                status="failed",
                error_code="RAG_SERVER_INGEST_SCRIPT_MISSING",
                error_message=f"missing RAG-SERVER ingest script: {ingest_script}",
            )

        python_executable = self.settings.rag_server.python_executable or sys.executable
        command = [
            python_executable,
            str(ingest_script),
            "--path",
            str(path),
            "--collection",
            collection or self.settings.rag_server.collection,
        ]
        if dry_run:
            command.append("--dry-run")

        try:
            completed = subprocess.run(
                command,
                cwd=str(repo_path),
                text=True,
                capture_output=True,
                timeout=timeout_seconds or self.settings.rag_server.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return IngestResult(
                status="failed",
                error_code="RAG_INGEST_TIMEOUT",
                error_message="rag server ingestion timed out",
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )

        return IngestResult(
            status="success" if completed.returncode == 0 else "failed",
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            error_code=None if completed.returncode == 0 else "RAG_INGEST_FAILED",
            error_message=None if completed.returncode == 0 else "rag server ingestion failed",
        )

