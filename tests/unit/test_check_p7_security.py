from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_p7_security.py"
SPEC = importlib.util.spec_from_file_location("check_p7_security", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_scan_redacts_detected_secret() -> None:
    secret = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2"

    findings = MODULE.scan_text("settings.py", f'api_key = "{secret}"\n')

    assert secret not in str(findings)
    assert {finding.rule for finding in findings} >= {
        "OPENAI_API_KEY"
    }


def test_scan_ignores_explicit_test_and_environment_placeholders() -> None:
    content = (
        "password: 'p7-test-password-32-characters'\n"
        "token: '${AI_SERVICE_TOKEN:?required}'\n"
    )

    findings = MODULE.scan_text("compose.yaml", content)

    assert findings == []


def test_scan_detects_private_key_header_without_returning_content() -> None:
    marker = "-----BEGIN " + "RSA PRIVATE KEY-----"

    findings = MODULE.scan_text("credential.pem", marker + "\n")

    assert findings == [
        MODULE.Finding(path="credential.pem", line=1, rule="PRIVATE_KEY")
    ]
    assert marker not in str(findings)


def test_candidate_files_supports_non_ascii_git_paths(tmp_path, monkeypatch) -> None:
    source = tmp_path / "\u4e2d\u6587.py"
    source.write_text("value = 1\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="\u4e2d\u6587.py\n", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)

    assert MODULE._candidate_files(tmp_path) == [source]
    assert captured["command"][:3] == ["git", "-c", "core.quotePath=false"]
    assert captured["kwargs"] == {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "surrogateescape",
        "check": False,
    }
