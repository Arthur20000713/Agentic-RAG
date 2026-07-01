from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import load_settings  # noqa: E402
from backend.app.evaluation.golden_runner import GoldenSetRunner  # noqa: E402
from backend.app.evaluation.multi_agent_runner import MultiAgentEvalRunner  # noqa: E402
from backend.app.evaluation.real_rag_runner import RealRagEvalRunner, RealRagEvalUnavailable  # noqa: E402
from backend.app.evaluation.v3_runner import V3EvalRunner  # noqa: E402
from backend.app.evaluation.v5_runner import V5EvalRunner  # noqa: E402


DEFAULT_GOLDEN_SET = "tests/fixtures/golden_set.json"
DEFAULT_V5_CASES = "tests/fixtures/v5_router_cases.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run V2 evaluation checks.")
    parser.add_argument(
        "--mode",
        choices=["fake", "real", "multi_agent", "v3", "v5"],
        default="fake",
        help="evaluation mode; real mode is optional and v3 mode compares V3 routing scenarios",
    )
    parser.add_argument("--golden-set", default=DEFAULT_GOLDEN_SET, help="path to golden set JSON")
    parser.add_argument("--output-dir", default="reports", help="directory for evaluation reports")
    parser.add_argument("--settings", default=None, help="settings YAML path for modes that use app settings")
    parser.add_argument("--batch", default=None, help="corpus batch YAML for real evaluation metadata and collection")
    parser.add_argument("--json", action="store_true", help="print JSON report to stdout")
    parser.add_argument(
        "--optional",
        action="store_true",
        help="allow optional real evaluation to skip when not implemented or not configured",
    )
    args = parser.parse_args(argv)

    if args.mode == "real":
        settings = load_settings(args.settings) if args.settings else None
        runner = RealRagEvalRunner(args.golden_set, output_dir=args.output_dir, settings=settings, batch=args.batch)
        try:
            report = runner.run()
        except RealRagEvalUnavailable as exc:
            if args.optional:
                runner.write_skipped_report(exc)
                if args.json:
                    print(json.dumps(exc.to_payload(), ensure_ascii=False, indent=2))
                else:
                    print(f"SKIPPED: {exc.message}")
                return 0
            print(f"ERROR: {exc.message}", file=sys.stderr)
            return 2
        runner.write_outputs(report)
        if args.json:
            print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        return 0 if report.metrics["failed_cases"] == 0 else 1

    if args.mode == "multi_agent":
        runner = MultiAgentEvalRunner(args.golden_set, output_dir=args.output_dir)
        report = runner.run()
        runner.write_outputs(report)
        if args.json:
            print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        return 0 if report.metrics["failed_cases"] == 0 else 1

    if args.mode == "v3":
        runner = V3EvalRunner(args.golden_set, output_dir=args.output_dir)
        report = runner.run()
        runner.write_outputs(report)
        if args.json:
            print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        return 0 if report.metrics["failed_cases"] == 0 else 1

    if args.mode == "v5":
        cases_path = DEFAULT_V5_CASES if args.golden_set == DEFAULT_GOLDEN_SET else args.golden_set
        runner = V5EvalRunner(cases_path, output_dir=args.output_dir)
        report = runner.run()
        runner.write_outputs(report)
        if args.json:
            print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        return 0 if report.metrics["failed_cases"] == 0 else 1

    runner = GoldenSetRunner(args.golden_set, output_dir=args.output_dir)
    report = runner.run()
    runner.write_outputs(report)

    if args.json:
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))

    return 0 if report.metrics["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
