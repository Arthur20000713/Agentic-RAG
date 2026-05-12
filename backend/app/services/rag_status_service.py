from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.health import resolve_rag_server_path


class RagStatusService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_rag_status(self) -> dict:
        repo_path = resolve_rag_server_path(self.settings)
        path_configured = repo_path is not None
        path_exists = bool(repo_path and repo_path.exists())
        uses_real = self.settings.rag_server.uses_real_rag_server

        last_error = None
        if uses_real and not path_configured:
            last_error = "RAG_SERVER_PATH_MISSING"
        elif uses_real and not path_exists:
            last_error = "RAG_SERVER_PATH_NOT_FOUND"

        return {
            "rag_mode": self.settings.rag_server.query_mode,
            "rag_mode_effective": self.settings.rag_server.normalized_query_mode,
            "strict_real_mode": self.settings.rag_server.strict_real_mode,
            "rag_server_path_configured": path_configured,
            "rag_server_path_exists": path_exists,
            "mcp_available": uses_real and path_exists,
            "default_collection": self.settings.rag_server.collection,
            "last_rag_error": last_error,
        }
