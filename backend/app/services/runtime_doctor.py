from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.integrations.rag_server.health import resolve_rag_server_path
from backend.app.services.feature_flag_service import FeatureFlagService


class RuntimeDoctor:
    def __init__(self, settings: Settings, *, project_root: Path = PROJECT_ROOT) -> None:
        self.settings = settings
        self.project_root = project_root

    def check(self, *, port: int | None = None) -> dict[str, Any]:
        checks = {
            "default_real_rag": self._check_default_real_rag(),
            "rag_server_path": self._check_rag_server_path(),
            "rag_server_python": self._check_rag_server_python(),
            "quality_gate": self._check_quality_gate(),
            "v3_shadow_path": self._check_v3_shadow_path(),
        }
        if port is not None:
            checks["port"] = self._check_port(port)

        status = "passed" if all(item["status"] == "passed" for item in checks.values()) else "failed"
        return {
            "status": status,
            "app": self.settings.app.name,
            "environment": self.settings.app.environment,
            "checks": checks,
        }

    def _check_default_real_rag(self) -> dict[str, Any]:
        rag = self.settings.rag_server
        passed = (
            rag.normalized_query_mode == "real"
            and rag.collection == "livestock_v4_2"
            and rag.strict_real_mode is True
        )
        return {
            "status": "passed" if passed else "failed",
            "query_mode": rag.query_mode,
            "effective_mode": rag.normalized_query_mode,
            "collection": rag.collection,
            "strict_real_mode": rag.strict_real_mode,
            "error_code": None if passed else "DEFAULT_REAL_RAG_NOT_CONFIGURED",
        }

    def _check_rag_server_path(self) -> dict[str, Any]:
        repo_path = resolve_rag_server_path(self.settings)
        passed = repo_path is not None and repo_path.exists()
        return {
            "status": "passed" if passed else "failed",
            "path": str(repo_path) if repo_path is not None else None,
            "exists": bool(repo_path and repo_path.exists()),
            "error_code": None if passed else "RAG_SERVER_PATH_INVALID",
        }

    def _check_rag_server_python(self) -> dict[str, Any]:
        raw_path = self.settings.rag_server.python_executable
        python_path = Path(raw_path) if raw_path else None
        passed = python_path is not None and python_path.exists()
        return {
            "status": "passed" if passed else "failed",
            "path": str(python_path) if python_path is not None else None,
            "exists": bool(python_path and python_path.exists()),
            "error_code": None if passed else "RAG_SERVER_PYTHON_INVALID",
        }

    def _check_quality_gate(self) -> dict[str, Any]:
        report_path = self.project_root / "docs" / "rag_corpus" / "reports" / "batch_002_quality.md"
        if not report_path.exists():
            return {
                "status": "failed",
                "report_path": str(report_path),
                "quality_gate_status": "missing_report",
                "error_code": "QUALITY_REPORT_MISSING",
            }
        text = report_path.read_text(encoding="utf-8").lower()
        passed = "quality gate: passed" in text and "80/80 passed" in text
        return {
            "status": "passed" if passed else "failed",
            "report_path": str(report_path),
            "quality_gate_status": "passed" if passed else "not_passed",
            "error_code": None if passed else "QUALITY_GATE_NOT_PASSED",
        }

    def _check_v3_shadow_path(self) -> dict[str, Any]:
        flags = FeatureFlagService(self.settings).snapshot()
        local_takeover_enabled = flags.model_router_low_risk_takeover_enabled
        passed = (
            flags.v3_enabled
            and flags.model_router_enabled
            and flags.model_router_shadow_mode
            and not local_takeover_enabled
            and self.settings.local_model.allow_final_answer is False
        )
        return {
            "status": "passed" if passed else "failed",
            "v3_enabled": flags.v3_enabled,
            "model_router_enabled": flags.model_router_enabled,
            "model_router_shadow_mode": flags.model_router_shadow_mode,
            "local_model_enabled": flags.local_model_enabled,
            "local_model_takeover_enabled": local_takeover_enabled,
            "local_model_allow_final_answer": self.settings.local_model.allow_final_answer,
            "error_code": None if passed else "V3_SHADOW_PATH_NOT_CONFIGURED",
        }

    def _check_port(self, port: int) -> dict[str, Any]:
        available = _port_available(port)
        return {
            "status": "passed" if available else "failed",
            "port": port,
            "available": available,
            "error_code": None if available else "PORT_IN_USE",
        }


def _port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0
