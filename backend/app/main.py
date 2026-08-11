from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import chat, conversations, documents, health, internal_v1, measurement, rag, tasks, traces
from backend.app.core.config import Settings, load_settings
from backend.app.core.errors import ErrorCode
from backend.app.core.internal_api import InternalApiError, request_id_or_new
from backend.app.core.response import ApiResponse
from backend.app.db.ai_execution_repository import AiExecutionRecordRepository
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import AgentTraceRepository, RagTraceRepository
from backend.app.integrations.rag_server import create_rag_server_client
from backend.app.schemas.internal_v1 import ErrorDetail, ErrorResponse
from backend.app.services.knowledge_ingestion_service import KnowledgeIngestionService
from backend.app.services.knowledge_ingestion_worker import KnowledgeIngestionWorker
from backend.app.services.trace_service import TraceService

# 挂载前端静态文件
def mount_frontend(app: FastAPI) -> None:
    frontend_dir = Path(__file__).with_name("static") / "frontend"
    if frontend_dir.exists():
        app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")


def create_app(settings: Settings | None = None) -> FastAPI:
    #加载配置并创建FastAPI
    app_settings = settings or load_settings()
    db_conn = get_connection(app_settings.database.url)
    init_db(db_conn)
    execution_db_conn = get_connection(
        app_settings.internal_api.execution_database_url or app_settings.database.url
    )
    init_db(execution_db_conn)
    trace_service = TraceService(
        RagTraceRepository(db_conn),
        AgentTraceRepository(db_conn),
    )
    internal_trace_service = TraceService(
        RagTraceRepository(execution_db_conn),
        AgentTraceRepository(execution_db_conn),
    )
    rag_client = create_rag_server_client(app_settings, trace_service=trace_service)
    execution_repository = AiExecutionRecordRepository(
        execution_db_conn,
        ttl_hours=app_settings.internal_api.execution_ttl_hours,
    )
    knowledge_ingestion_worker = KnowledgeIngestionWorker(
        execution_repository,
        KnowledgeIngestionService(app_settings),
        poll_interval_seconds=app_settings.internal_api.ingestion_poll_interval_seconds,
        lease_seconds=app_settings.internal_api.ingestion_lease_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if app_settings.internal_api.ingestion_worker_enabled:
            knowledge_ingestion_worker.start()
        try:
            yield
        finally:
            await knowledge_ingestion_worker.stop()
            close = getattr(rag_client, "close", None)
            if callable(close):
                close_result = close()
                if inspect.isawaitable(close_result):
                    await close_result
            db_conn.close()
            execution_db_conn.close()

    app = FastAPI(title=app_settings.app.name, lifespan=lifespan)

    #初始化共享资源：数据库、调用链追踪服务、调用RAG-SERVER的客户端
    app.state.settings = app_settings
    app.state.db_conn = db_conn
    app.state.execution_db_conn = execution_db_conn
    app.state.trace_service = trace_service
    app.state.internal_trace_service = internal_trace_service
    app.state.rag_client = rag_client
    app.state.ai_execution_repository = execution_repository
    app.state.knowledge_ingestion_worker = knowledge_ingestion_worker

    #注册了八组路由，把这组接口接入主应用
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(documents.router)
    app.include_router(health.router)
    app.include_router(rag.router)
    app.include_router(tasks.router)
    if app_settings.legacy_api.measurement_enabled:
        app.include_router(measurement.router)
    app.include_router(traces.router)
    app.include_router(internal_v1.router)
    app.include_router(internal_v1.health_router)
    mount_frontend(app)

    @app.exception_handler(InternalApiError)
    async def internal_api_exception_handler(request, exc: InternalApiError):  # noqa: ANN001
        request_id = request_id_or_new(request)
        payload = ErrorResponse(
            request_id=request_id,
            operation_id=exc.operation_id,
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            ),
        )
        headers = {"X-Request-ID": request_id}
        if exc.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(mode="json", by_alias=True),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):  # noqa: ANN001
        if request.url.path.startswith("/internal/v1"):
            request_id = request_id_or_new(request)
            malformed_json = any(error.get("type") == "json_invalid" for error in exc.errors())
            payload = ErrorResponse(
                request_id=request_id,
                error=ErrorDetail(
                    code="INVALID_REQUEST" if malformed_json else "SCHEMA_VALIDATION_FAILED",
                    message="invalid JSON request" if malformed_json else "request schema validation failed",
                    retryable=False,
                    details={
                        "violations": [
                            {
                                "location": [str(item) for item in error.get("loc", ())],
                                "type": error.get("type"),
                                "message": error.get("msg"),
                            }
                            for error in exc.errors()
                        ]
                    },
                ),
            )
            return JSONResponse(
                status_code=400 if malformed_json else 422,
                content=payload.model_dump(mode="json", by_alias=True),
                headers={"X-Request-ID": request_id},
            )
        response = ApiResponse.fail(
            ErrorCode.INVALID_REQUEST,
            "invalid request",
            data={"detail": exc.errors()},
        )
        return JSONResponse(status_code=200, content=response.model_dump())

    return app


app = create_app()
