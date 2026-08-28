from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from backend.app.core.internal_api import (
    InternalApiError,
    canonical_request_hash,
    require_matching_request_id,
    require_request_id,
    require_service_bearer,
    request_id_or_new,
)
from backend.app.schemas.internal_v1 import (
    AiOperation,
    ChatRequest,
    ChatResponse,
    ChatRun,
    CollectionListResponse,
    CollectionSummary,
    DocumentSummaryResponse,
    ErrorDetail,
    HealthCheck,
    KnowledgeIngestionAccepted,
    KnowledgeIngestionRequest,
    LivenessResponse,
    MeasurementAnalyzeRequest,
    MeasurementAnalyzeResponse,
    ReadinessResponse,
)
from backend.app.services.internal_ai_service import InternalAiService


PROTECTED_PREFIX = "/internal/v1"
router = APIRouter(
    prefix=PROTECTED_PREFIX,
    tags=["internal-v1"],
    dependencies=[Depends(require_service_bearer)],
)
health_router = APIRouter(prefix=f"{PROTECTED_PREFIX}/health", tags=["internal-v1-health"])


def _set_request_id(response: Response, request_id: str) -> None:
    response.headers["X-Request-ID"] = request_id


def _repository(request: Request):  # noqa: ANN202
    return request.app.state.ai_execution_repository


@router.post("/ai/chat", response_model=ChatResponse, response_model_by_alias=True)
async def create_ai_chat_run(
    payload: ChatRequest,
    request: Request,
    response: Response,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> ChatResponse:
    request_id = require_request_id(x_request_id)
    _set_request_id(response, request_id)
    require_matching_request_id(request_id, payload.request_id, operation_id=payload.operation_id)
    request_hash = canonical_request_hash(
        "AI_CHAT",
        payload.model_dump(mode="json", by_alias=True),
    )
    claim = _claim_execution(
        request,
        operation_id=payload.operation_id,
        idempotency_key=idempotency_key,
        operation_type="AI_CHAT",
        request_id=request_id,
        request_hash=request_hash,
    )
    if claim.state == "conflict":
        raise InternalApiError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "operation ID or idempotency key is already bound to another request",
            operation_id=payload.operation_id,
        )
    record = claim.record or {}
    if claim.state == "replay":
        return _replay_sync_result(record, response_type=ChatResponse)

    service = InternalAiService(
        request.app.state.rag_client,
        request.app.state.settings,
        request.app.state.internal_trace_service,
        checkpointer=getattr(request.app.state, "agent_checkpointer", None),
        memory_store=request.app.state.memory_store,
    )
    try:
        result = await asyncio.wait_for(
            service.chat(payload, run_id=record["run_id"]),
            timeout=payload.deadline_ms / 1000,
        )
    except asyncio.TimeoutError as exc:
        error = _error_detail(
            "DEADLINE_EXCEEDED",
            "AI chat deadline exceeded",
            retryable=True,
            http_status=504,
        )
        _fail_execution(request, payload.operation_id, error.model_dump(by_alias=True))
        raise InternalApiError(
            504,
            error.code,
            error.message,
            retryable=error.retryable,
            operation_id=payload.operation_id,
        ) from exc
    except Exception as exc:
        error = _error_detail(
            "AI_SERVICE_UNAVAILABLE",
            "AI chat execution failed",
            retryable=True,
            http_status=503,
        )
        _fail_execution(request, payload.operation_id, error.model_dump(by_alias=True))
        raise InternalApiError(
            503,
            error.code,
            error.message,
            retryable=error.retryable,
            operation_id=payload.operation_id,
        ) from exc
    serialized = result.model_dump(mode="json", by_alias=True)
    _complete_execution(request, payload.operation_id, serialized)
    return result


@router.get("/ai/runs/{operationId}", response_model=ChatRun, response_model_by_alias=True)
async def get_ai_chat_run(
    request: Request,
    response: Response,
    operation_id: str = Path(
        alias="operationId",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> ChatRun:
    request_id = require_request_id(x_request_id)
    _set_request_id(response, request_id)
    record = _get_execution(request, operation_id)
    if record is None or record["operation_type"] != "AI_CHAT":
        raise InternalApiError(
            404,
            "OPERATION_NOT_FOUND",
            "AI chat operation not found",
            operation_id=operation_id,
        )
    return ChatRun(
        request_id=request_id,
        operation_id=record["operation_id"],
        run_id=record["run_id"],
        status=record["status"],
        result=record["result"],
        error=record["error"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        expires_at=record["expires_at"],
    )


@router.post(
    "/ai/measurements/analyze",
    response_model=MeasurementAnalyzeResponse,
    response_model_by_alias=True,
)
async def analyze_measurement(
    payload: MeasurementAnalyzeRequest,
    request: Request,
    response: Response,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> MeasurementAnalyzeResponse:
    request_id = require_request_id(x_request_id)
    _set_request_id(response, request_id)
    require_matching_request_id(request_id, payload.request_id, operation_id=payload.operation_id)
    claim = _claim_execution(
        request,
        operation_id=payload.operation_id,
        idempotency_key=idempotency_key,
        operation_type="AI_MEASUREMENT",
        request_id=request_id,
        request_hash=canonical_request_hash(
            "AI_MEASUREMENT",
            payload.model_dump(mode="json", by_alias=True),
        ),
    )
    if claim.state == "conflict":
        raise InternalApiError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "operation ID or idempotency key is already bound to another request",
            operation_id=payload.operation_id,
        )
    record = claim.record or {}
    if claim.state == "replay":
        return _replay_sync_result(record, response_type=MeasurementAnalyzeResponse)

    service = InternalAiService(
        request.app.state.rag_client,
        request.app.state.settings,
        request.app.state.internal_trace_service,
        checkpointer=getattr(request.app.state, "agent_checkpointer", None),
        memory_store=request.app.state.memory_store,
    )
    try:
        result = await asyncio.wait_for(
            service.analyze_measurement(payload, run_id=record["run_id"]),
            timeout=payload.deadline_ms / 1000,
        )
    except asyncio.TimeoutError as exc:
        error = _error_detail(
            "DEADLINE_EXCEEDED",
            "measurement deadline exceeded",
            retryable=True,
            http_status=504,
        )
        _fail_execution(request, payload.operation_id, error.model_dump(by_alias=True))
        raise InternalApiError(
            504,
            error.code,
            error.message,
            retryable=True,
            operation_id=payload.operation_id,
        ) from exc
    except Exception as exc:
        error = _error_detail(
            "AI_SERVICE_UNAVAILABLE",
            "measurement execution failed",
            retryable=True,
            http_status=503,
        )
        _fail_execution(request, payload.operation_id, error.model_dump(by_alias=True))
        raise InternalApiError(
            503,
            error.code,
            error.message,
            retryable=error.retryable,
            operation_id=payload.operation_id,
        ) from exc
    _complete_execution(
        request,
        payload.operation_id,
        result.model_dump(mode="json", by_alias=True),
    )
    return result


@router.post(
    "/ai/knowledge/ingestions",
    response_model=KnowledgeIngestionAccepted,
    response_model_by_alias=True,
    status_code=202,
)
async def create_knowledge_ingestion(
    payload: KnowledgeIngestionRequest,
    request: Request,
    response: Response,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
) -> KnowledgeIngestionAccepted:
    request_id = require_request_id(x_request_id)
    _set_request_id(response, request_id)
    require_matching_request_id(request_id, payload.request_id, operation_id=payload.operation_id)
    claim = _claim_execution(
        request,
        operation_id=payload.operation_id,
        idempotency_key=idempotency_key,
        operation_type="DOCUMENT_INDEX",
        request_id=request_id,
        request_hash=canonical_request_hash(
            "DOCUMENT_INDEX",
            payload.model_dump(mode="json", by_alias=True),
        ),
        initial_status="ACCEPTED",
        request_payload=payload.model_dump(mode="json", by_alias=True),
    )
    if claim.state == "conflict":
        raise InternalApiError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "operation ID or idempotency key is already bound to another request",
            operation_id=payload.operation_id,
        )
    record = claim.record or {}
    response.headers["Location"] = f"/internal/v1/ai/operations/{payload.operation_id}"
    return KnowledgeIngestionAccepted(
        request_id=request_id,
        operation_id=record["operation_id"],
        run_id=record["run_id"],
        status=record["status"],
        submitted_at=record["created_at"],
    )


@router.get("/ai/operations/{operationId}", response_model=AiOperation, response_model_by_alias=True)
async def get_ai_operation(
    request: Request,
    response: Response,
    operation_id: str = Path(
        alias="operationId",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> AiOperation:
    request_id = require_request_id(x_request_id)
    _set_request_id(response, request_id)
    record = _get_execution(request, operation_id)
    if record is None or record["operation_type"] != "DOCUMENT_INDEX":
        raise InternalApiError(
            404,
            "OPERATION_NOT_FOUND",
            "AI operation not found",
            operation_id=operation_id,
        )
    return AiOperation(
        request_id=request_id,
        operation_id=record["operation_id"],
        run_id=record["run_id"],
        status=record["status"],
        progress=record["progress"],
        result=record["result"],
        error=record["error"],
        created_at=record["created_at"],
        started_at=record["started_at"],
        updated_at=record["updated_at"],
        finished_at=record["finished_at"],
        expires_at=record["expires_at"],
    )


@router.get("/rag/collections", response_model=CollectionListResponse, response_model_by_alias=True)
async def list_rag_collections(
    request: Request,
    response: Response,
    include_stats: bool = Query(default=True, alias="includeStats"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> CollectionListResponse:
    request_id = require_request_id(x_request_id)
    _set_request_id(response, request_id)
    try:
        names = await request.app.state.rag_client.list_collections(include_stats=include_stats)
    except Exception as exc:
        raise InternalApiError(
            503,
            "RAG_UNAVAILABLE",
            "RAG collections are unavailable",
            retryable=True,
        ) from exc
    return CollectionListResponse(
        request_id=request_id,
        collections=[CollectionSummary(name=name) for name in names],
        raw_response_id=None,
    )


@router.get(
    "/rag/collections/{collection}/documents/{docId}/summary",
    response_model=DocumentSummaryResponse,
    response_model_by_alias=True,
)
async def get_rag_document_summary(
    request: Request,
    response: Response,
    collection: str = Path(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
    doc_id: str = Path(
        alias="docId",
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> DocumentSummaryResponse:
    request_id = require_request_id(x_request_id)
    _set_request_id(response, request_id)
    try:
        summary = await request.app.state.rag_client.get_document_summary(
            doc_id,
            collection=collection,
        )
    except Exception as exc:
        raise InternalApiError(
            503,
            "RAG_UNAVAILABLE",
            "RAG document summary is unavailable",
            retryable=True,
        ) from exc
    if not summary.summary:
        raise InternalApiError(
            404,
            "DOCUMENT_NOT_FOUND",
            "RAG document not found",
        )
    return DocumentSummaryResponse(
        request_id=request_id,
        collection=collection,
        document_id=summary.doc_id,
        title=summary.title,
        summary=summary.summary,
        tags=summary.tags,
        source=summary.source,
        chunk_count=summary.chunk_count,
        source_uri_prefix=f"rag://{quote(collection, safe='-_.~')}/{quote(summary.doc_id, safe='-_.~')}",
        raw_response_id=None,
    )


@health_router.get("/liveness", response_model=LivenessResponse, response_model_by_alias=True)
async def get_liveness(
    request: Request,
    response: Response,
) -> LivenessResponse:
    request_id = request_id_or_new(request)
    _set_request_id(response, request_id)
    return LivenessResponse(
        request_id=request_id,
        version="0.1.0",
        timestamp=datetime.now(timezone.utc),
    )


@health_router.get("/readiness", response_model=ReadinessResponse, response_model_by_alias=True)
async def get_readiness(
    request: Request,
    response: Response,
) -> ReadinessResponse:
    request_id = request_id_or_new(request)
    _set_request_id(response, request_id)
    checks: dict[str, HealthCheck] = {}
    try:
        request.app.state.execution_db_conn.execute(
            "SELECT operation_id FROM ai_execution_record LIMIT 1"
        ).fetchone()
        checks["executionStore"] = HealthCheck(status="UP")
    except Exception:
        checks["executionStore"] = HealthCheck(
            status="DOWN",
            code="EXECUTION_STORE_UNAVAILABLE",
            message="execution store unavailable",
        )

    token = request.app.state.settings.internal_api.service_token
    checks["serviceAuthentication"] = HealthCheck(
        status="UP" if token is not None and token.get_secret_value() else "DOWN",
        code=None if token is not None and token.get_secret_value() else "SERVICE_TOKEN_MISSING",
        message=None if token is not None and token.get_secret_value() else "service token is not configured",
    )

    try:
        collections = await request.app.state.rag_client.list_collections(include_stats=False)
        target = request.app.state.settings.rag_server.collection
        if request.app.state.settings.rag_server.uses_real_rag_server and target not in collections:
            checks["rag"] = HealthCheck(
                status="DOWN",
                code="COLLECTION_NOT_FOUND",
                message="configured RAG collection is unavailable",
            )
        else:
            checks["rag"] = HealthCheck(status="UP")
    except Exception:
        checks["rag"] = HealthCheck(
            status="DOWN",
            code="RAG_UNAVAILABLE",
            message="RAG dependency unavailable",
        )

    ready = all(check.status == "UP" for check in checks.values())
    response.status_code = 200 if ready else 503
    return ReadinessResponse(
        request_id=request_id,
        status="READY" if ready else "NOT_READY",
        checks=checks,
        timestamp=datetime.now(timezone.utc),
    )


def _replay_sync_result(record: dict, *, response_type):  # noqa: ANN001, ANN202
    if record.get("status") == "SUCCEEDED" and isinstance(record.get("result"), dict):
        return response_type.model_validate(record["result"])
    if record.get("status") == "FAILED":
        error = record.get("error") or {}
        details = error.get("details") if isinstance(error.get("details"), dict) else {}
        status_code = details.get("httpStatus")
        if not isinstance(status_code, int) or status_code not in {400, 409, 422, 429, 502, 503, 504}:
            status_code = 503
        raise InternalApiError(
            status_code,
            str(error.get("code") or "AI_SERVICE_UNAVAILABLE"),
            str(error.get("message") or "previous AI execution failed"),
            retryable=bool(error.get("retryable")),
            operation_id=record.get("operation_id"),
        )
    raise InternalApiError(
        429,
        "CONCURRENCY_LIMITED",
        "operation is already running",
        retryable=True,
        operation_id=record.get("operation_id"),
    )


def _claim_execution(request: Request, **kwargs):  # noqa: ANN003, ANN202
    try:
        return _repository(request).claim(**kwargs)
    except Exception as exc:
        raise InternalApiError(
            503,
            "EXECUTION_STORE_UNAVAILABLE",
            "AI execution store unavailable",
            retryable=True,
            operation_id=kwargs.get("operation_id"),
        ) from exc


def _get_execution(request: Request, operation_id: str) -> dict | None:
    try:
        return _repository(request).get(operation_id)
    except Exception as exc:
        raise InternalApiError(
            503,
            "EXECUTION_STORE_UNAVAILABLE",
            "AI execution store unavailable",
            retryable=True,
            operation_id=operation_id,
        ) from exc


def _complete_execution(
    request: Request,
    operation_id: str,
    result: dict,
) -> dict:
    try:
        return _repository(request).complete(operation_id, result)
    except Exception as exc:
        raise InternalApiError(
            503,
            "EXECUTION_STORE_UNAVAILABLE",
            "AI execution result could not be persisted",
            retryable=True,
            operation_id=operation_id,
        ) from exc


def _fail_execution(
    request: Request,
    operation_id: str,
    error: dict,
) -> dict:
    try:
        return _repository(request).fail(operation_id, error)
    except Exception as exc:
        raise InternalApiError(
            503,
            "EXECUTION_STORE_UNAVAILABLE",
            "AI execution failure could not be persisted",
            retryable=True,
            operation_id=operation_id,
        ) from exc


def _error_detail(
    code: str,
    message: str,
    *,
    retryable: bool,
    http_status: int,
) -> ErrorDetail:
    return ErrorDetail(
        code=code,
        message=message,
        retryable=retryable,
        details={"httpStatus": http_status},
    )
