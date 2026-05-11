from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local project checks.")
    parser.add_argument("--unit-only", action="store_true", help="run only unit tests")
    args = parser.parse_args()

    command = [sys.executable, "-m", "pytest"]
    if args.unit_only:
        command.append("tests/unit")
        completed = subprocess.run(command, check=False)
        return completed.returncode

    command.extend(["-m", "not rag_server"])
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        return completed.returncode

    eval_command = [sys.executable, str(Path(__file__).with_name("run_eval.py"))]
    eval_completed = subprocess.run(eval_command, check=False)
    return eval_completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
