from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile

from backend.app.core.response import ApiResponse
from backend.app.db.repositories import RagIngestionTaskRepository
from backend.app.services.document_service import DocumentService


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    collection: str = Form("default"),
) -> dict:
    service = DocumentService(RagIngestionTaskRepository(request.app.state.db_conn))
    data = await service.upload_document(file, collection=collection)
    return ApiResponse.ok(data).model_dump()

