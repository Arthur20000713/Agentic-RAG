from __future__ import annotations

import os
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT, Settings


def resolve_rag_server_path(
    settings: Settings | None = None,
    *,
    project_root: Path = PROJECT_ROOT,
) -> Path | None:
    raw_path = os.getenv("RAG_SERVER_PATH")
    if raw_path is None and settings is not None:
        raw_path = settings.rag_server.repo_path
    if not raw_path:
        return None

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()

