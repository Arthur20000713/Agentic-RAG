from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.errors import ErrorCode
from backend.app.core.response import ApiResponse
from backend.app.db.repositories import RagIngestionTaskRepository
from backend.app.integrations.rag_server.cli_gateway import RagServerCliGateway
from backend.app.services.task_service import TaskService


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _service(request: Request) -> TaskService:
    return TaskService(
        RagIngestionTaskRepository(request.app.state.db_conn),
        RagServerCliGateway(request.app.state.settings),
    )


@router.get("/{task_id}")
async def get_task(task_id: str, request: Request) -> dict:
    task = _service(request).get_task(task_id)
    if task is None:
        return ApiResponse.fail(ErrorCode.NOT_FOUND, "task not found").model_dump()
    return ApiResponse.ok(task).model_dump()


@router.post("/{task_id}/index")
async def index_document_via_rag_server(task_id: str, request: Request) -> dict:
    result = _service(request).index_document_via_rag_server(task_id)
    if result.get("status") == "not_found":
        return ApiResponse.fail(ErrorCode.NOT_FOUND, "task not found", data=result).model_dump()
    if result.get("status") == "failed":
        return ApiResponse.fail(ErrorCode.RAG_INGESTION_FAILED, "rag ingestion failed", data=result).model_dump()
    return ApiResponse.ok(result).model_dump()

