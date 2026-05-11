from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.evaluation.golden_runner import GoldenSetRunner  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local fake golden-set evaluation.")
    parser.add_argument("--golden-set", default="tests/fixtures/golden_set.json", help="path to golden set JSON")
    parser.add_argument("--output-dir", default="reports", help="directory for evaluation reports")
    parser.add_argument("--json", action="store_true", help="print JSON report to stdout")
    args = parser.parse_args(argv)

    runner = GoldenSetRunner(args.golden_set, output_dir=args.output_dir)
    report = runner.run()
    runner.write_outputs(report)

    if args.json:
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))

    return 0 if report.metrics["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
