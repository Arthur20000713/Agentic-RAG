from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backend.app.core.config import PROJECT_ROOT
from backend.app.db.repositories import RagIngestionTaskRepository


class DocumentService:
    def __init__(
        self,
        task_repository: RagIngestionTaskRepository,
        *,
        upload_dir: Path | None = None,
    ) -> None:
        self.task_repository = task_repository
        self.upload_dir = upload_dir or PROJECT_ROOT / "data" / "uploads"

    async def upload_document(self, file: UploadFile, *, collection: str = "default") -> dict:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        task_id = f"task_{uuid4().hex}"
        filename = self._safe_filename(file.filename or "upload.bin")
        target = self.upload_dir / f"{task_id}_{filename}"
        content = await file.read()
        target.write_bytes(content)
        self.task_repository.create(task_id, str(target), collection)
        return {
            "task_id": task_id,
            "document_path": str(target),
            "collection": collection,
            "status": "pending",
        }

    def _safe_filename(self, filename: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
        return cleaned or "upload.bin"

