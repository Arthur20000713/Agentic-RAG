from __future__ import annotations

import subprocess
import sys


def test_query_script_outputs_fake_rag_citations() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/query.py",
            "--query",
            "犊牛腹泻的常见原因是什么？",
            "--top-k",
            "1",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "犊牛腹泻防治技术手册" in completed.stdout
    assert "参考依据" in completed.stdout


def test_ingest_via_rag_server_reports_missing_path() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/ingest_via_rag_server.py",
            "--path",
            "demo.pdf",
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "RAG_SERVER_PATH_MISSING" in completed.stdout

