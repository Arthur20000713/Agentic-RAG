from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request

from backend.app.core.errors import ErrorCode
from backend.app.core.response import ApiResponse
from backend.app.services.rag_status_service import RagStatusService


router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/status")
async def get_rag_status(request: Request) -> dict:
    service = RagStatusService(request.app.state.settings)
    return ApiResponse.ok(service.get_rag_status()).model_dump()


@router.get("/collections")
async def list_rag_collections(request: Request, include_stats: bool = True) -> dict:
    status_service = RagStatusService(request.app.state.settings)
    rag_status = status_service.get_rag_status()
    if request.app.state.settings.rag_server.uses_real_rag_server and rag_status["last_rag_error"]:
        return ApiResponse.fail(
            ErrorCode.RAG_SERVER_UNAVAILABLE,
            "rag server unavailable",
            data={
                "collections": [],
                "status": "error",
                "error_code": rag_status["last_rag_error"],
                "raw_response_id": None,
            },
        ).model_dump()

    try:
        names = await request.app.state.rag_client.list_collections(include_stats=include_stats)
    except Exception:
        return ApiResponse.fail(
            ErrorCode.RAG_SERVER_UNAVAILABLE,
            "rag server collections query failed",
            data={
                "collections": [],
                "status": "error",
                "error_code": "RAG_COLLECTIONS_FAILED",
                "raw_response_id": None,
            },
        ).model_dump()

    return ApiResponse.ok(
        {
            "collections": [
                {
                    "name": name,
                    "description": None,
                    "document_count": None,
                    "updated_at": None,
                }
                for name in names
            ],
            "status": "success",
            "error_code": None,
            "raw_response_id": None,
        }
    ).model_dump()


@router.get("/collections/{collection}/documents/{doc_id}/summary")
async def get_rag_document_summary(request: Request, collection: str, doc_id: str) -> dict:
    status_service = RagStatusService(request.app.state.settings)
    rag_status = status_service.get_rag_status()
    if request.app.state.settings.rag_server.uses_real_rag_server and rag_status["last_rag_error"]:
        return ApiResponse.fail(
            ErrorCode.RAG_SERVER_UNAVAILABLE,
            "rag server unavailable",
            data={
                "doc_id": doc_id,
                "collection": collection,
                "summary": None,
                "status": "error",
                "error_code": rag_status["last_rag_error"],
                "raw_response_id": None,
            },
        ).model_dump()

    try:
        summary = await request.app.state.rag_client.get_document_summary(doc_id, collection=collection)
    except Exception:
        return ApiResponse.fail(
            ErrorCode.RAG_SERVER_UNAVAILABLE,
            "rag server document summary query failed",
            data={
                "doc_id": doc_id,
                "collection": collection,
                "summary": None,
                "status": "error",
                "error_code": "RAG_DOCUMENT_SUMMARY_FAILED",
                "raw_response_id": None,
            },
        ).model_dump()

    return ApiResponse.ok(
        {
            "doc_id": summary.doc_id,
            "collection": collection,
            "title": summary.title,
            "summary": summary.summary,
            "tags": summary.tags,
            "source": summary.source,
            "chunk_count": summary.chunk_count,
            "source_uri_prefix": f"rag://{quote(collection, safe='-_.~')}/{quote(summary.doc_id, safe='-_.~')}",
            "status": "success",
            "error_code": None,
            "raw_response_id": None,
        }
    ).model_dump()
