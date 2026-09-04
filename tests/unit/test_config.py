from __future__ import annotations

from uuid import uuid4
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.core.config import load_settings
from backend.app.integrations.rag_server import FakeRagServerClient, RagServerMcpClient, create_rag_server_client
from backend.app.integrations.rag_server.health import resolve_rag_server_path
from backend.app.services.feature_flag_service import FeatureFlagService


def _test_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_test_settings_default_to_fake_rag_client() -> None:
    settings = load_settings("config/settings.test.yaml")

    assert settings.rag_server.query_mode == "fake"
    assert isinstance(create_rag_server_client(settings), FakeRagServerClient)


def test_rag_server_path_prefers_environment(monkeypatch) -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text(
        "rag_server:\n  query_mode: fake\n  repo_path: from_config\n",
        encoding="utf-8",
    )
    env_path = root / "from_env"
    monkeypatch.setenv("RAG_SERVER_PATH", str(env_path))

    settings = load_settings(config_path)
    resolved = resolve_rag_server_path(settings, project_root=root)

    assert resolved == env_path.resolve()


def test_settings_path_can_be_selected_by_environment(monkeypatch) -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text("app:\n  environment: browser-test\n", encoding="utf-8")
    monkeypatch.setenv("APP_SETTINGS_PATH", str(config_path))

    settings = load_settings()

    assert settings.app.environment == "browser-test"


def test_runtime_paths_and_database_can_be_overridden_for_containers(monkeypatch) -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "rag_server:",
                "  query_mode: real",
                "  repo_path: from-config",
                "  python_executable: from-config-python",
                "  collection: from-config-collection",
                "database:",
                "  url: sqlite:///from-config.db",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RAG_SERVER_PATH", "/opt/rag-server")
    monkeypatch.setenv("RAG_QUERY_MODE", "fake")
    monkeypatch.setenv("RAG_SERVER_PYTHON", "/opt/rag-server/.venv/bin/python")
    monkeypatch.setenv("RAG_COLLECTION", "livestock_container")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////var/lib/livestock-ai/operations.db")

    settings = load_settings(config_path)

    assert settings.rag_server.repo_path == "/opt/rag-server"
    assert settings.rag_server.query_mode == "fake"
    assert settings.rag_server.python_executable == "/opt/rag-server/.venv/bin/python"
    assert settings.rag_server.collection == "livestock_container"
    assert settings.database.url == "sqlite:////var/lib/livestock-ai/operations.db"


def test_internal_service_settings_use_secret_and_environment_overrides(monkeypatch) -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("AI_SERVICE_TOKEN", "service-token-that-must-not-be-printed")
    monkeypatch.setenv("AI_EXECUTION_TTL_HOURS", "48")
    monkeypatch.setenv("AI_EXECUTION_DATABASE_URL", "sqlite:////data/ai_execution.db")
    monkeypatch.setenv("SHARED_UPLOAD_ROOT", "/data/uploads")

    settings = load_settings(config_path)

    assert settings.internal_api.service_token is not None
    assert settings.internal_api.service_token.get_secret_value() == "service-token-that-must-not-be-printed"
    assert str(settings.internal_api.service_token) == "**********"
    assert settings.internal_api.execution_ttl_hours == 48
    assert settings.internal_api.execution_database_url == "sqlite:////data/ai_execution.db"
    assert settings.internal_api.shared_upload_root == "/data/uploads"


def test_relative_rag_server_path_resolves_from_project_root(monkeypatch) -> None:
    root = _test_dir()
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    config_path = root / "settings.yaml"
    config_path.write_text(
        "rag_server:\n  query_mode: fake\n  repo_path: sibling-rag\n",
        encoding="utf-8",
    )
    settings = load_settings(config_path)

    assert resolve_rag_server_path(settings, project_root=root) == (root / "sibling-rag").resolve()


def test_rag_query_modes_load_without_parallel_rag_config(monkeypatch) -> None:
    root = _test_dir()
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "rag_server:",
                "  query_mode: smoke",
                "  repo_path: sibling-rag",
                "  strict_real_mode: true",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.rag_server.query_mode == "smoke"
    assert settings.rag_server.normalized_query_mode == "smoke"
    assert settings.rag_server.uses_real_rag_server is True
    assert settings.rag_server.strict_real_mode is True
    assert resolve_rag_server_path(settings, project_root=root) == (root / "sibling-rag").resolve()


def test_rag_low_confidence_policy_defaults_do_not_change_fake_mode() -> None:
    settings = load_settings("config/settings.test.yaml")

    assert settings.rag_server.min_mapped_score == 0.03
    assert settings.rag_server.min_citation_count_for_answer == 1
    assert settings.rag_server.low_confidence_no_answer is True
    assert settings.rag_server.query_mode == "fake"
    assert isinstance(create_rag_server_client(settings), FakeRagServerClient)


def test_rag_low_confidence_policy_can_be_configured() -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "rag_server:",
                "  query_mode: real",
                "  min_mapped_score: 0.42",
                "  min_citation_count_for_answer: 2",
                "  low_confidence_no_answer: false",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.rag_server.min_mapped_score == 0.42
    assert settings.rag_server.min_citation_count_for_answer == 2
    assert settings.rag_server.low_confidence_no_answer is False


def test_legacy_mcp_stdio_query_mode_remains_supported() -> None:
    settings = load_settings("config/settings.test.yaml")
    settings.rag_server.query_mode = "mcp_stdio"

    assert settings.rag_server.normalized_query_mode == "real"
    assert settings.rag_server.uses_real_rag_server is True
    assert isinstance(create_rag_server_client(settings), RagServerMcpClient)


def test_real_query_mode_uses_mcp_client() -> None:
    settings = load_settings("config/settings.test.yaml")
    settings.rag_server.query_mode = "real"

    assert settings.rag_server.normalized_query_mode == "real"
    assert isinstance(create_rag_server_client(settings), RagServerMcpClient)


def test_agent_runtime_defaults_to_langgraph() -> None:
    settings = load_settings("config/settings.test.yaml")

    assert settings.agent_runtime.engine == "langgraph"
    assert settings.model_router.enabled is False
    assert settings.model_router.shadow_mode is True
    assert settings.model_router.allow_low_risk_takeover is False
    assert settings.local_model.enabled is False
    assert settings.local_model.provider == "mock"
    assert settings.local_model.endpoint is None
    assert settings.local_model.model is None
    assert settings.local_model.device == "auto"
    assert settings.local_model.torch_dtype == "auto"
    assert settings.local_model.max_new_tokens == 128
    assert settings.local_model.temperature == 0
    assert settings.lora.dataset_enabled is False
    assert settings.lora.inference_enabled is False
    assert settings.long_term_memory.write_enabled is False
    assert settings.long_term_memory.read_enabled is False
    assert settings.enhanced_safety.precheck_enabled is True
    assert settings.enhanced_safety.final_guard_required is True
    assert settings.primary_llm.enabled is False
    assert settings.primary_llm.provider == "mock"
    assert settings.primary_llm.api_key_env == "PRIMARY_LLM_API_KEY"
    assert settings.disease_llm.enabled is False
    assert settings.disease_llm.shadow_mode is True
    assert settings.disease_llm.require_rag_evidence is True
    assert settings.disease_llm.allow_rule_fallback is True
    assert isinstance(create_rag_server_client(settings), FakeRagServerClient)


def test_product_settings_keep_langgraph_runtime_without_slow_chat_local_takeover() -> None:
    settings = load_settings("config/settings.yaml")
    snapshot = FeatureFlagService(settings).snapshot()

    assert snapshot.agent_runtime_engine == "langgraph"
    assert snapshot.model_router_enabled is True
    assert snapshot.model_router_shadow_mode is False
    assert snapshot.model_router_low_risk_takeover_enabled is True
    assert snapshot.local_model_enabled is True
    assert snapshot.primary_llm_enabled is True
    assert snapshot.disease_llm_enabled is True
    assert settings.model_router.allow_low_risk_takeover is True
    assert "intent_routing" not in settings.model_router.takeover_task_types
    assert "query_normalization" not in settings.model_router.takeover_task_types
    assert "measurement_analysis" in settings.model_router.takeover_task_types
    assert settings.local_model.provider == "ollama"
    assert settings.local_model.model == "qwen2.5:7b"
    assert settings.local_model.allow_final_answer is False
    assert settings.primary_llm.provider == "openai"
    assert settings.primary_llm.model == "gpt-5.6-luna"
    assert settings.primary_llm.base_url == "https://api.a6api.com"
    assert settings.primary_llm.api_key_env == "A6API_API_KEY"
    assert settings.disease_llm.shadow_mode is False


def test_agent_runtime_settings_load_from_existing_config_root() -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "agent_runtime:",
                "  engine: langgraph",
                "model_router:",
                "  enabled: true",
                "  shadow_mode: true",
                "  allow_low_risk_takeover: false",
                "local_model:",
                "  enabled: true",
                "  provider: mock",
                "  timeout_seconds: 2",
                "lora:",
                "  dataset_enabled: true",
                "  inference_enabled: false",
                "  registry_path: data/model_registry/test_registry.json",
                "long_term_memory:",
                "  write_enabled: true",
                "  read_enabled: false",
                "  ttl_days: 30",
                "enhanced_safety:",
                "  precheck_enabled: true",
                "  final_guard_required: true",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.agent_runtime.engine == "langgraph"
    assert settings.model_router.enabled is True
    assert settings.model_router.shadow_mode is True
    assert settings.local_model.enabled is True
    assert settings.local_model.timeout_seconds == 2
    assert settings.lora.dataset_enabled is True
    assert settings.lora.registry_path == "data/model_registry/test_registry.json"
    assert settings.long_term_memory.write_enabled is True
    assert settings.long_term_memory.ttl_days == 30


def test_legacy_v3_top_level_config_is_rejected() -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text("v3:\n  enabled: true\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="v3"):
        load_settings(config_path)


def test_v5_local_model_settings_load_real_backend_fields() -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "local_model:",
                "  enabled: true",
                "  provider: ollama",
                "  endpoint: http://127.0.0.1:11434",
                "  model: qwen2.5:7b-instruct",
                "  timeout_seconds: 8",
                "  max_retries: 1",
                "  allow_final_answer: false",
                "  device: cuda:0",
                "  torch_dtype: float16",
                "  max_new_tokens: 96",
                "  temperature: 0",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.local_model.enabled is True
    assert settings.local_model.provider == "ollama"
    assert settings.local_model.endpoint == "http://127.0.0.1:11434"
    assert settings.local_model.model == "qwen2.5:7b-instruct"
    assert settings.local_model.timeout_seconds == 8
    assert settings.local_model.max_retries == 1
    assert settings.local_model.allow_final_answer is False
    assert settings.local_model.device == "cuda:0"
    assert settings.local_model.torch_dtype == "float16"
    assert settings.local_model.max_new_tokens == 96
    assert settings.local_model.temperature == 0


def test_primary_llm_and_disease_llm_settings_load_without_key_value() -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "primary_llm:",
                "  enabled: true",
                "  provider: deepseek",
                "  model: deepseek-v4-flash",
                "  base_url: https://api.deepseek.com",
                "  api_key_env: DEEPSEEK_API_KEY",
                "  timeout_seconds: 30",
                "  max_retries: 1",
                "disease_llm:",
                "  enabled: true",
                "  shadow_mode: true",
                "  require_rag_evidence: true",
                "  allow_rule_fallback: true",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.primary_llm.enabled is True
    assert settings.primary_llm.provider == "deepseek"
    assert settings.primary_llm.model == "deepseek-v4-flash"
    assert settings.primary_llm.base_url == "https://api.deepseek.com"
    assert settings.primary_llm.api_key_env == "DEEPSEEK_API_KEY"
    assert settings.primary_llm.timeout_seconds == 30
    assert settings.primary_llm.max_retries == 1
    assert settings.disease_llm.enabled is True
    assert settings.disease_llm.shadow_mode is True
    assert settings.disease_llm.require_rag_evidence is True
    assert settings.disease_llm.allow_rule_fallback is True


def test_project_settings_declare_llm_sections_without_secret_values() -> None:
    for path in ("config/settings.yaml", "config/settings.test.yaml", "config/settings.v5.example.yaml"):
        settings = load_settings(path)

        assert settings.primary_llm.api_key_env is not None
        assert not hasattr(settings.primary_llm, "api_key")
        assert settings.disease_llm.require_rag_evidence is True
        assert settings.disease_llm.allow_rule_fallback is True
