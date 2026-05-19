from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.core.config import PROJECT_ROOT


class LoraTrainingConfig(BaseModel):
    base_model: str = Field(min_length=1)
    dataset_path: str = Field(min_length=1)
    output_dir: str = Field(min_length=1)
    adapter_name: str = Field(min_length=1)
    training_script: str = Field(min_length=1)
    python_executable: str = "python"
    max_steps: int = Field(default=100, gt=0)
    extra_args: list[str] = Field(default_factory=list)


class LoraTrainingReport(BaseModel):
    status: str
    executed: bool
    adapter_name: str
    output_dir: str
    command: list[str]
    return_code: int | None = None
    error_message: str | None = None


def build_training_command(config: LoraTrainingConfig) -> list[str]:
    _ensure_output_outside_repo(config.output_dir)
    command = [
        config.python_executable,
        config.training_script,
        "--base-model",
        config.base_model,
        "--dataset",
        config.dataset_path,
        "--output-dir",
        config.output_dir,
        "--adapter-name",
        config.adapter_name,
        "--max-steps",
        str(config.max_steps),
    ]
    command.extend(config.extra_args)
    return command


def run_lora_training(config: LoraTrainingConfig, *, dry_run: bool = True) -> LoraTrainingReport:
    command = build_training_command(config)
    if dry_run:
        return LoraTrainingReport(
            status="dry_run",
            executed=False,
            adapter_name=config.adapter_name,
            output_dir=config.output_dir,
            command=command,
        )

    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return LoraTrainingReport(
        status="passed" if completed.returncode == 0 else "failed",
        executed=True,
        adapter_name=config.adapter_name,
        output_dir=config.output_dir,
        command=command,
        return_code=completed.returncode,
        error_message=_safe_error_message(completed.stderr) if completed.returncode != 0 else None,
    )


def _ensure_output_outside_repo(output_dir: str) -> None:
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    try:
        output_path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return
    raise ValueError("output_dir must be outside the repository")


def _safe_error_message(stderr: str) -> str:
    return stderr.strip()[:500]
