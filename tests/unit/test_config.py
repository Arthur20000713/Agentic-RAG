from __future__ import annotations

from uuid import uuid4
from pathlib import Path

from backend.app.core.config import load_settings
from backend.app.integrations.rag_server import FakeRagServerClient, RagServerMcpClient, create_rag_server_client
from backend.app.integrations.rag_server.health import resolve_rag_server_path


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


def test_v2_rag_query_modes_load_without_parallel_rag_config(monkeypatch) -> None:
    root = _test_dir()
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "rag:",
                "  rag_server_path: ignored",
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


def test_v3_settings_default_to_disabled_without_changing_v2_behavior() -> None:
    settings = load_settings("config/settings.test.yaml")

    assert settings.v3.enabled is False
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
    assert isinstance(create_rag_server_client(settings), FakeRagServerClient)


def test_v3_settings_can_be_enabled_from_existing_config_root() -> None:
    root = _test_dir()
    config_path = root / "settings.yaml"
    config_path.write_text(
        "\n".join(
            [
                "v3:",
                "  enabled: true",
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
                "  registry_path: data/v3/test_registry.json",
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

    assert settings.v3.enabled is True
    assert settings.model_router.enabled is True
    assert settings.model_router.shadow_mode is True
    assert settings.local_model.enabled is True
    assert settings.local_model.timeout_seconds == 2
    assert settings.lora.dataset_enabled is True
    assert settings.lora.registry_path == "data/v3/test_registry.json"
    assert settings.long_term_memory.write_enabled is True
    assert settings.long_term_memory.ttl_days == 30


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
