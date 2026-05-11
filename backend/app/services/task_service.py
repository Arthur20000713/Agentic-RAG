from __future__ import annotations

from backend.app.db.repositories import RagIngestionTaskRepository
from backend.app.integrations.rag_server.cli_gateway import RagServerCliGateway


class TaskService:
    def __init__(
        self,
        task_repository: RagIngestionTaskRepository,
        cli_gateway: RagServerCliGateway,
    ) -> None:
        self.task_repository = task_repository
        self.cli_gateway = cli_gateway

    def get_task(self, task_id: str) -> dict | None:
        return self.task_repository.get(task_id)

    def index_document_via_rag_server(self, task_id: str) -> dict:
        task = self.task_repository.get(task_id)
        if task is None:
            return {"status": "not_found", "task_id": task_id, "error_code": "TASK_NOT_FOUND"}

        self.task_repository.update_status(task_id, "running")
        result = self.cli_gateway.ingest(
            task["document_path"],
            collection=task["collection"],
            dry_run=False,
        )
        if result.status == "success":
            self.task_repository.update_status(task_id, "success")
            updated = self.task_repository.get(task_id) or {}
            updated["error_code"] = None
            return updated

        self.task_repository.update_status(task_id, "failed", error_message=result.error_message)
        updated = self.task_repository.get(task_id) or {}
        updated["error_code"] = result.error_code
        updated["stderr"] = result.stderr
        return updated

