from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.api import chat, documents, measurement, tasks
from backend.app.core.config import Settings, load_settings
from backend.app.core.errors import ErrorCode
from backend.app.core.response import ApiResponse
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.integrations.rag_server import create_rag_server_client


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or load_settings()
    app = FastAPI(title=app_settings.app.name)
    app.state.settings = app_settings
    app.state.db_conn = get_connection(app_settings.database.url)
    init_db(app.state.db_conn)
    app.state.rag_client = create_rag_server_client(app_settings)

    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(tasks.router)
    app.include_router(measurement.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):  # noqa: ANN001
        response = ApiResponse.fail(
            ErrorCode.INVALID_REQUEST,
            "invalid request",
            data={"detail": exc.errors()},
        )
        return JSONResponse(status_code=200, content=response.model_dump())

    return app


app = create_app()
