from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings, resolve_project_path
from backend.app.integrations.rag_server.cli_gateway import RagServerCliGateway


@dataclass(frozen=True)
class KnowledgeIngestionFailure(Exception):
    code: str
    message: str
    retryable: bool = False
    timed_out: bool = False


class KnowledgeIngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.shared_root = resolve_project_path(settings.internal_api.shared_upload_root)
        self.gateway = RagServerCliGateway(settings)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._validated_path(payload)
        if not self.settings.rag_server.uses_real_rag_server:
            return self._result(payload, indexed=False, skipped=False, chunk_count=0, execution_mode="FAKE")

        ingest = self.gateway.ingest(
            path,
            collection=payload["collection"],
            timeout_seconds=self.settings.internal_api.ingestion_timeout_seconds,
        )
        if ingest.status != "success":
            raise KnowledgeIngestionFailure(
                code=ingest.error_code or "RAG_INGEST_FAILED",
                message=ingest.error_message or "rag server ingestion failed",
                retryable=ingest.error_code in {"RAG_INGEST_TIMEOUT", "RAG_SERVER_PATH_MISSING"},
                timed_out=ingest.error_code == "RAG_INGEST_TIMEOUT",
            )
        output = f"{ingest.stdout}\n{ingest.stderr}".lower()
        skipped = "skip" in output
        return self._result(
            payload,
            indexed=not skipped,
            skipped=skipped,
            chunk_count=None,
            execution_mode="REAL",
        )

    def _validated_path(self, payload: dict[str, Any]) -> Path:
        root = self.shared_root.resolve(strict=True)
        object_key = payload["objectKey"]
        candidate = root
        for segment in object_key.split("/"):
            candidate = candidate / segment
            if candidate.is_symlink():
                raise KnowledgeIngestionFailure("OBJECT_KEY_SYMLINK", "symbolic links are not allowed")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, ValueError) as exc:
            code = "OBJECT_NOT_FOUND" if isinstance(exc, FileNotFoundError) else "OBJECT_KEY_OUTSIDE_ROOT"
            raise KnowledgeIngestionFailure(code, "document object is unavailable") from exc
        if not resolved.is_file():
            raise KnowledgeIngestionFailure("OBJECT_NOT_REGULAR_FILE", "document object is not a regular file")

        expected_media = {".pdf": "application/pdf", ".txt": "text/plain"}
        suffix = Path(payload["fileName"]).suffix.lower()
        if suffix not in expected_media or expected_media[suffix] != payload["mediaType"]:
            raise KnowledgeIngestionFailure("UNSUPPORTED_MEDIA_TYPE", "document type is not supported")
        if resolved.suffix.lower() != suffix:
            raise KnowledgeIngestionFailure("FILE_EXTENSION_MISMATCH", "object extension does not match file name")
        if resolved.stat().st_size != payload["sizeBytes"]:
            raise KnowledgeIngestionFailure("OBJECT_SIZE_MISMATCH", "document size does not match metadata")

        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            prefix = stream.read(5)
            digest.update(prefix)
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != payload["sha256"]:
            raise KnowledgeIngestionFailure("OBJECT_HASH_MISMATCH", "document hash does not match metadata")
        if suffix == ".pdf" and prefix != b"%PDF-":
            raise KnowledgeIngestionFailure("INVALID_PDF", "PDF signature is invalid")
        if suffix == ".txt":
            try:
                resolved.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise KnowledgeIngestionFailure("INVALID_TEXT_ENCODING", "text document must be UTF-8") from exc
        return resolved

    @staticmethod
    def _result(
        payload: dict[str, Any],
        *,
        indexed: bool,
        skipped: bool,
        chunk_count: int | None,
        execution_mode: str,
    ) -> dict[str, Any]:
        return {
            "documentId": payload["documentId"],
            "ragDocumentId": payload["sha256"],
            "collection": payload["collection"],
            "indexed": indexed,
            "skipped": skipped,
            "chunkCount": chunk_count,
            "executionMode": execution_mode,
        }
