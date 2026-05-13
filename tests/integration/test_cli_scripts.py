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


def test_check_v2_offline_passes() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v2.py",
            "--offline",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V2 checks passed" in completed.stdout


def test_check_v3_stage_0_passes_without_real_rag() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v3.py",
            "--stage",
            "0",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V3 checks passed for stage 0" in completed.stdout
    assert "RAG_SERVER_PATH_MISSING" not in completed.stderr


def test_check_v3_accepts_full_stage_baseline() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v3.py",
            "--stage",
            "full",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V3 checks passed for stage full" in completed.stdout
