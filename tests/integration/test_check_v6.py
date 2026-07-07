from __future__ import annotations

import subprocess
import sys


def test_check_v6_baseline_cli_passes_for_current_repo() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v6.py",
            "--stage",
            "baseline",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V6 checks passed for stage baseline" in completed.stdout

