from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.lora.trainer import LoraTrainingConfig, run_lora_training  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or dry-run local LoRA adapter training.")
    parser.add_argument("--config", required=True, help="LoRA training YAML config")
    parser.add_argument("--dry-run", action="store_true", help="generate command without executing training")
    parser.add_argument("--execute", action="store_true", help="execute the configured training command")
    parser.add_argument("--json", action="store_true", help="print report JSON")
    args = parser.parse_args(argv)

    if args.execute and args.dry_run:
        print("FAIL: choose either --dry-run or --execute", file=sys.stderr)
        return 1

    try:
        config = _load_config(args.config)
        report = run_lora_training(config, dry_run=not args.execute)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(f"{report.status}: adapter={report.adapter_name}")
    return 0 if report.status in {"dry_run", "passed"} else 1


def _load_config(path: str | Path) -> LoraTrainingConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("LoRA training config must be a mapping")
    return LoraTrainingConfig.model_validate(payload)


if __name__ == "__main__":
    raise SystemExit(main())
