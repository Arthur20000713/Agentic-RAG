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
