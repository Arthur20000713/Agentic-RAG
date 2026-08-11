from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from backend.app.core.config import Settings
from backend.app.services.runtime_doctor import RuntimeDoctor


def _test_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()

def test_runtime_doctor_reports_langgraph_local_structured_takeover_path() -> None:
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": ".",
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "strict_real_mode": True,
        },
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True, "allow_final_answer": False},
    )

    report = RuntimeDoctor(settings).check()

    assert report["checks"]["agent_runtime"]["status"] == "passed"
    assert report["checks"]["agent_runtime"]["engine"] == "langgraph"
    assert report["checks"]["agent_runtime"]["model_router_shadow_mode"] is False
    assert report["checks"]["agent_runtime"]["local_model_takeover_enabled"] is True
    assert report["checks"]["disease_llm_path"]["status"] == "passed"
    assert report["checks"]["disease_llm_path"]["disease_llm_enabled"] is False


def test_runtime_doctor_reports_local_model_acceptance() -> None:
    tmp_path = _test_dir()
    report_path = tmp_path / "docs" / "local_model" / "transformers_smoke_report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        """
{
  "status": "passed",
  "provider": "transformers",
  "model": "Qwen/Qwen2.5-0.5B-Instruct",
  "cases": [
    {"task_type": "query_normalization", "status": "passed", "fallback_required": false}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": ".",
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "strict_real_mode": True,
        },
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={
            "enabled": True,
            "provider": "transformers",
            "model": "Qwen/Qwen2.5-0.5B-Instruct",
            "allow_final_answer": False,
        },
    )

    report = RuntimeDoctor(settings, project_root=tmp_path).check()

    acceptance = report["checks"]["local_model_acceptance"]
    assert acceptance["status"] == "passed"
    assert acceptance["provider"] == "transformers"
    assert acceptance["model"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert acceptance["query_normalization_smoke"] == "passed"


def test_runtime_doctor_fails_disease_llm_takeover_without_primary_llm_config() -> None:
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": ".",
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "strict_real_mode": True,
        },
        disease_llm={"enabled": True, "shadow_mode": False},
        primary_llm={"enabled": False, "provider": "mock"},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True, "allow_final_answer": False},
    )

    report = RuntimeDoctor(settings).check()

    disease_llm = report["checks"]["disease_llm_path"]
    assert disease_llm["status"] == "failed"
    assert disease_llm["takeover_enabled"] is True
    assert disease_llm["primary_llm_configured"] is False
    assert disease_llm["error_code"] == "DISEASE_LLM_TAKEOVER_PRIMARY_LLM_NOT_CONFIGURED"


def test_runtime_doctor_accepts_disease_llm_takeover_with_rag_server_env_key(monkeypatch) -> None:
    tmp_path = _test_dir()
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    rag_server = tmp_path / "RAG-SERVER"
    rag_server.mkdir()
    (rag_server / ".env").write_text("DEEPSEEK_API_KEY=secret-from-rag-server\n", encoding="utf-8")
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(rag_server),
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "strict_real_mode": True,
        },
        disease_llm={"enabled": True, "shadow_mode": False},
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
        },
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True, "allow_final_answer": False},
    )

    disease_llm = RuntimeDoctor(settings)._check_disease_llm_path()

    assert disease_llm["status"] == "passed"
    assert disease_llm["takeover_enabled"] is True
    assert disease_llm["primary_llm_configured"] is True
    assert disease_llm["primary_llm_api_key_present"] is True
    assert "secret-from-rag-server" not in str(disease_llm)
