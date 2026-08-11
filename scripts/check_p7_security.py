"""Redaction-safe source secret scanner used by the V7 release gate."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


TEXT_SUFFIXES = {
    ".env",
    ".java",
    ".js",
    ".json",
    ".md",
    ".pem",
    ".properties",
    ".ps1",
    ".py",
    ".toml",
    ".xml",
    ".key",
    ".yaml",
    ".yml",
}
IGNORED_PARTS = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp",
    ".tmp_tests",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "logs",
    "reports",
    "target",
}
PLACEHOLDER_MARKERS = {
    "changeme",
    "change-me",
    "dummy",
    "example",
    "fake",
    "not-a-real",
    "placeholder",
    "sample",
    "test",
    "your-",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str


KNOWN_SECRET_RULES = (
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("AWS_ACCESS_KEY", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])")),
    ("GITHUB_TOKEN", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,}(?![A-Za-z0-9])")),
    ("OPENAI_API_KEY", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")),
    ("SLACK_TOKEN", re.compile(r"(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{20,}(?![A-Za-z0-9-])")),
)
GENERIC_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key)"
    r"\s*[=:]\s*[\"']([^\"'\r\n]{16,})[\"']"
)


def _entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _is_placeholder(value: str, relative_path: str) -> bool:
    lowered = value.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return True
    if any(marker in value for marker in ("${", "$env:", "{{", "}}")):
        return True
    test_path = "/test/" in f"/{relative_path.lower()}/" or relative_path.lower().startswith("tests/")
    obvious_test_value = any(
        marker in lowered
        for marker in (
            "audit",
            "integration",
            "password",
            "secret",
            "token",
        )
    ) or "0123456789" in value
    return test_path and obvious_test_value


def _candidate_files(root: Path) -> list[Path]:
    command = [
        "git",
        "-c",
        "core.quotePath=false",
        "-C",
        str(root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        check=False,
    )
    if completed.returncode == 0:
        candidates = [root / item for item in completed.stdout.splitlines() if item]
    else:
        candidates = list(root.rglob("*"))
    return sorted(
        path
        for path in candidates
        if path.is_file()
        and not any(part in IGNORED_PARTS for part in path.relative_to(root).parts)
        and (path.name.startswith(".env") or path.suffix.lower() in TEXT_SUFFIXES)
    )


def scan_text(relative: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in KNOWN_SECRET_RULES:
            match = pattern.search(line)
            if match and not _is_placeholder(match.group(0), relative):
                findings.append(Finding(relative, line_number, rule))
        for match in GENERIC_ASSIGNMENT.finditer(line):
            value = match.group(1).strip()
            if not _is_placeholder(value, relative) and _entropy(value) >= 3.5:
                findings.append(Finding(relative, line_number, "HIGH_ENTROPY_SECRET"))
    return findings


def scan_tree(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _candidate_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(root).as_posix()
        findings.extend(scan_text(relative, content))
    return sorted(set(findings), key=lambda item: (item.path, item.line, item.rule))


def build_report(root: Path) -> dict[str, object]:
    findings = scan_tree(root)
    return {
        "status": "PASS" if not findings else "FAIL",
        "scanner": "p7-redaction-safe-source-secret-scan",
        "root": str(root),
        "findingCount": len(findings),
        "findings": [asdict(finding) for finding in findings],
        "redacted": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    report = build_report(root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
