from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import Settings, load_settings  # noqa: E402
from backend.app.model.local_client import LocalModelClient  # noqa: E402


@dataclass(frozen=True)
class LocalModelSmokeCase:
    task_type: str
    status: str
    fallback_required: bool
    error_code: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class LocalModelSmokeReport:
    status: str
    provider: str
    model: str | None
    endpoint_configured: bool
    reason: str | None = None
    cases: list[LocalModelSmokeCase] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SMOKE_TASKS = (
    ("query_normalization", "What feed should I use for a calf after weaning?"),
    ("slot_extraction", "Extract low-risk livestock slots from: calf has mild cough"),
)


async def run_smoke(settings: Settings) -> LocalModelSmokeReport:
    provider = settings.local_model.provider
    model = settings.local_model.model
    endpoint_configured = bool(settings.local_model.endpoint)
    if not _has_real_local_model_config(settings):
        return LocalModelSmokeReport(
            status="skipped",
            provider=provider,
            model=model,
            endpoint_configured=endpoint_configured,
            reason="real local model is not configured",
        )

    client = LocalModelClient(settings)
    cases: list[LocalModelSmokeCase] = []
    for task_type, prompt in _smoke_tasks(settings):
        try:
            payload = await client.generate_json(prompt, schema_name=task_type)
        except Exception as exc:
            cases.append(
                LocalModelSmokeCase(
                    task_type=task_type,
                    status="failed",
                    fallback_required=True,
                    error_code="LOCAL_MODEL_SMOKE_ERROR",
                    reason=str(exc) or exc.__class__.__name__,
                )
            )
            continue

        fallback_required = bool(payload.get("fallback_required"))
        case_status = "passed" if payload.get("status") == "success" and not fallback_required else "failed"
        cases.append(
            LocalModelSmokeCase(
                task_type=task_type,
                status=case_status,
                fallback_required=fallback_required,
                error_code=payload.get("error_code"),
                reason=payload.get("reason"),
            )
        )

    report_status = "passed" if all(case.status == "passed" for case in cases) else "failed"
    return LocalModelSmokeReport(
        status=report_status,
        provider=provider,
        model=model,
        endpoint_configured=endpoint_configured,
        cases=cases,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run optional real local model smoke checks.")
    parser.add_argument("--settings", default=None, help="settings YAML path")
    parser.add_argument("--output", default="reports/local_model_smoke.json", help="output report path")
    parser.add_argument("--optional", action="store_true", help="return 0 when real local model is not configured")
    args = parser.parse_args(argv)

    settings = load_settings(args.settings)
    report = asyncio.run(run_smoke(settings))
    _write_report(Path(args.output), report)

    if report.status == "passed":
        print(f"PASSED: local model smoke provider={report.provider}")
        return 0
    if report.status == "skipped":
        print(f"SKIPPED: {report.reason}")
        return 0 if args.optional else 2

    print("FAILED: local model smoke failed", file=sys.stderr)
    return 1


def _has_real_local_model_config(settings: Settings) -> bool:
    if settings.local_model.provider == "transformers":
        return (
            settings.local_model.enabled
            and bool(settings.local_model.model)
        )
    return (
        settings.local_model.enabled
        and settings.local_model.provider != "mock"
        and bool(settings.local_model.endpoint)
        and bool(settings.local_model.model)
    )


def _smoke_tasks(settings: Settings) -> tuple[tuple[str, str], ...]:
    if settings.local_model.provider == "transformers":
        return (SMOKE_TASKS[0],)
    return SMOKE_TASKS


def _write_report(path: Path, report: LocalModelSmokeReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
