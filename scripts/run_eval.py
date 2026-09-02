from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import load_settings  # noqa: E402
from backend.app.evaluation.agent_runtime_runner import (
    AgentRuntimeEvalRunner,
)
from backend.app.evaluation.golden_runner import GoldenSetRunner  # noqa: E402
from backend.app.evaluation.multi_agent_runner import MultiAgentEvalRunner  # noqa: E402
from backend.app.evaluation.real_rag_runner import (  # noqa: E402
    RealRagEvalRunner,
    RealRagEvalUnavailable,
)
from backend.app.evaluation.v5_runner import V5EvalRunner  # noqa: E402

DEFAULT_GOLDEN_SET = "tests/fixtures/golden_set.json"
DEFAULT_V5_CASES = "tests/fixtures/v5_router_cases.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Agentic RAG evaluation checks.")
    parser.add_argument(
        "--mode",
        choices=["fake", "real", "multi_agent", "agent_runtime", "v5"],
        default="fake",
        help="evaluation mode; real mode is optional and agent_runtime mode compares LangGraph routing scenarios",
    )
    parser.add_argument("--golden-set", default=DEFAULT_GOLDEN_SET, help="path to golden set JSON")
    parser.add_argument("--output-dir", default="reports", help="directory for evaluation reports")
    parser.add_argument("--settings", default=None, help="settings YAML path for modes that use app settings")
    parser.add_argument("--batch", default=None, help="corpus batch YAML for real evaluation metadata and collection")
    parser.add_argument("--json", action="store_true", help="print JSON report to stdout")
    parser.add_argument(
        "--agent-runtime-real",
        action="store_true",
        help="run agent_runtime with configured real RAG/local/primary models; never falls back to fake",
    )
    parser.add_argument("--warmup-runs", type=int, default=None, help="warm-up runs per router scenario")
    parser.add_argument("--repeats", type=int, default=None, help="measured repeats per case and router scenario")
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

    if args.mode == "agent_runtime":
        settings = load_settings(args.settings) if args.settings else None
        golden_set = (
            "tests/fixtures/router_ab_golden.json"
            if args.golden_set == DEFAULT_GOLDEN_SET
            else args.golden_set
        )
        warmup_runs = args.warmup_runs if args.warmup_runs is not None else (1 if args.agent_runtime_real else 0)
        measured_repeats = args.repeats if args.repeats is not None else (3 if args.agent_runtime_real else 1)
        rag_client = None
        try:
            if args.agent_runtime_real:
                real_runner = RealRagEvalRunner(golden_set, output_dir=args.output_dir, settings=settings)
                settings = real_runner.settings
                rag_client = real_runner.create_rag_client()
            runner = AgentRuntimeEvalRunner(
                golden_set,
                output_dir=args.output_dir,
                rag_client=rag_client,
                base_settings=settings,
                evidence_kind="real" if args.agent_runtime_real else "scripted",
                warmup_runs=warmup_runs,
                measured_repeats=measured_repeats,
            )
            report = runner.run()
            runner.write_outputs(report)
        except (RealRagEvalUnavailable, ValueError) as exc:
            if not args.optional:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
            _write_agent_runtime_skipped(Path(args.output_dir), str(exc))
            print(f"SKIPPED: {exc}")
            return 0
        finally:
            if rag_client is not None:
                close = getattr(rag_client, "close", None)
                if close is not None:
                    asyncio.run(close())
        if args.json:
            print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        gate_passed = report.metrics["quality_gate"]["passed"] if args.agent_runtime_real else True
        return 0 if report.metrics["failed_cases"] == 0 and gate_passed else 1

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


def _write_agent_runtime_skipped(output_dir: Path, reason: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "skipped",
        "mode": "agent_runtime",
        "evidence_kind": "real",
        "performance_claim_allowed": False,
        "reason": reason,
    }
    (output_dir / "eval_result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
