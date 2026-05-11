from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local project checks.")
    parser.add_argument("--unit-only", action="store_true", help="run only unit tests")
    args = parser.parse_args()

    command = [sys.executable, "-m", "pytest"]
    if args.unit_only:
        command.append("tests/unit")
    else:
        command.extend(["-m", "not rag_server"])

    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

