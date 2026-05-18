from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.evaluation.quality_gate import load_eval_report
from backend.app.evaluation.report_diff import compare_eval_reports, render_metric_delta_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two eval_result.json reports.")
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    before = load_eval_report(_resolve_path(args.before))
    after = load_eval_report(_resolve_path(args.after))
    markdown = render_metric_delta_markdown(compare_eval_reports(before, after))
    if args.output is not None:
        output_path = _resolve_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT / path


if __name__ == "__main__":
    raise SystemExit(main())
