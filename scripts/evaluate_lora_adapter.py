from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.lora.registry import ModelRegistry  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a registered LoRA adapter.")
    parser.add_argument("--registry", required=True, help="model registry JSON path")
    parser.add_argument("--model-id", required=True, help="registered model id")
    parser.add_argument("--optional", action="store_true", help="skip when registry/model is unavailable")
    args = parser.parse_args(argv)

    registry_path = Path(args.registry)
    if not registry_path.exists():
        return _skip_or_fail(args.optional, f"registry not found: {registry_path}")

    model = ModelRegistry(registry_path).get_model(args.model_id)
    if model is None:
        return _skip_or_fail(args.optional, f"model not found: {args.model_id}")

    report = {
        "status": "skipped",
        "model_id": model.model_id,
        "reason": "real LoRA adapter evaluation backend is not configured",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if args.optional else 2


def _skip_or_fail(optional: bool, reason: str) -> int:
    if optional:
        print(f"SKIPPED: {reason}")
        return 0
    print(f"FAIL: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
