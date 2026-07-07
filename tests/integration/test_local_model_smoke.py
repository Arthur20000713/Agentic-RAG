from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from backend.app.core.config import Settings
from scripts import run_local_model_smoke


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_run_local_model_smoke_optional_skips_without_real_config() -> None:
    output = _tmp_dir() / "local_model_smoke.json"

    exit_code = run_local_model_smoke.main(
        ["--settings", "config/settings.test.yaml", "--optional", "--output", str(output)]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert payload["provider"] == "mock"
    assert payload["reason"] == "real local model is not configured"


def test_run_local_model_smoke_requires_optional_for_missing_config() -> None:
    output = _tmp_dir() / "local_model_smoke.json"

    exit_code = run_local_model_smoke.main(["--settings", "config/settings.test.yaml", "--output", str(output)])

    assert exit_code == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"


def test_run_smoke_uses_configured_real_provider(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        async def generate_json(self, prompt: str, *, schema_name: str, context=None):
            calls.append((prompt, schema_name))
            return {
                "status": "success",
                "schema_name": schema_name,
                "fallback_required": False,
                "provider": "ollama",
            }

    monkeypatch.setattr(run_local_model_smoke, "LocalModelClient", FakeClient)
    settings = Settings(
        local_model={
            "enabled": True,
            "provider": "ollama",
            "endpoint": "http://127.0.0.1:11434",
            "model": "qwen2.5:7b-instruct",
        }
    )

    report = asyncio.run(run_local_model_smoke.run_smoke(settings))

    assert report.status == "passed"
    assert report.provider == "ollama"
    assert report.model == "qwen2.5:7b-instruct"
    assert [case.task_type for case in report.cases] == ["query_normalization", "slot_extraction"]
    assert calls == [
        ("What feed should I use for a calf after weaning?", "query_normalization"),
        ("Extract low-risk livestock slots from: calf has mild cough", "slot_extraction"),
    ]


def test_run_smoke_uses_query_normalization_only_for_transformers(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        async def generate_json(self, prompt: str, *, schema_name: str, context=None):
            calls.append((prompt, schema_name))
            return {
                "status": "success",
                "schema_name": schema_name,
                "fallback_required": False,
                "provider": "transformers",
            }

    monkeypatch.setattr(run_local_model_smoke, "LocalModelClient", FakeClient)
    settings = Settings(
        local_model={
            "enabled": True,
            "provider": "transformers",
            "model": "Qwen/Qwen2.5-0.5B-Instruct",
        }
    )

    report = asyncio.run(run_local_model_smoke.run_smoke(settings))

    assert report.status == "passed"
    assert report.provider == "transformers"
    assert [case.task_type for case in report.cases] == ["query_normalization"]
    assert calls == [("What feed should I use for a calf after weaning?", "query_normalization")]
