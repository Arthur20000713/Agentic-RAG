from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import load_settings  # noqa: E402
from backend.app.services.runtime_doctor import RuntimeDoctor  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run V6 runtime diagnostics.")
    parser.add_argument("--settings", default=None, help="settings YAML path")
    parser.add_argument("--port", type=int, default=None, help="port to check before startup")
    parser.add_argument("--json", action="store_true", help="print JSON payload")
    args = parser.parse_args(argv)

    report = RuntimeDoctor(load_settings(args.settings)).check(port=args.port)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"V6 runtime doctor: {report['status']}")
        for name, check in report["checks"].items():
            suffix = f" ({check['error_code']})" if check.get("error_code") else ""
            print(f"- {name}: {check['status']}{suffix}")

    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

