from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.config import PROJECT_ROOT
from backend.app.lora.trainer import LoraTrainingConfig, build_training_command, run_lora_training


def _config(output_dir: str = "C:/tmp/lora_adapters/calf_slots") -> LoraTrainingConfig:
    return LoraTrainingConfig(
        base_model="qwen2.5:7b-instruct",
        dataset_path="C:/tmp/lora_dataset/dataset.json",
        output_dir=output_dir,
        adapter_name="calf_slots_v1",
        training_script="C:/tmp/train_lora.py",
        max_steps=20,
    )


def test_build_training_command_uses_structured_args() -> None:
    command = build_training_command(_config())

    assert command == [
        "python",
        "C:/tmp/train_lora.py",
        "--base-model",
        "qwen2.5:7b-instruct",
        "--dataset",
        "C:/tmp/lora_dataset/dataset.json",
        "--output-dir",
        "C:/tmp/lora_adapters/calf_slots",
        "--adapter-name",
        "calf_slots_v1",
        "--max-steps",
        "20",
    ]


def test_run_lora_training_dry_run_returns_report_without_execution() -> None:
    report = run_lora_training(_config(), dry_run=True)

    assert report.status == "dry_run"
    assert report.executed is False
    assert report.adapter_name == "calf_slots_v1"
    assert report.command[0] == "python"


def test_lora_training_rejects_output_dir_inside_repo() -> None:
    repo_output = PROJECT_ROOT / "data" / "v5" / "lora_adapters" / "bad"
    config = _config(str(repo_output))

    with pytest.raises(ValueError, match="output_dir must be outside the repository"):
        build_training_command(config)
