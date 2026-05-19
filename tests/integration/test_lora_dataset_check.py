from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from scripts.check_lora_dataset import check_lora_dataset, main


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _example(example_id: str = "lora_001") -> dict:
    return {
        "example_id": example_id,
        "task_type": "slot_extraction",
        "instruction": "Extract slots.",
        "input_text": "Calf diarrhea.",
        "output_text": "{}",
        "source": "rule_generated",
        "safety_level": "S1",
        "metadata": {"intent": "disease_consultation"},
    }


def test_check_lora_dataset_requires_test_split() -> None:
    path = _tmp_dir() / "dataset.json"
    path.write_text(json.dumps({"train": [_example()], "validation": [_example("lora_002")]}, ensure_ascii=False), encoding="utf-8")

    failures = check_lora_dataset(path)

    assert failures == ["dataset missing non-empty split: test"]


def test_check_lora_dataset_rejects_forbidden_fields_without_leaking_values(capsys) -> None:  # noqa: ANN001
    path = _tmp_dir() / "dataset.json"
    payload = {
        "train": [_example()],
        "validation": [_example("lora_002")],
        "test": [
            {
                **_example("lora_003"),
                "metadata": {"api_key": "secret-value-that-must-not-print"},
                "raw_rag_text": "copied private document text",
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--input", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "api_key" in captured.err
    assert "raw_rag_text" in captured.err
    assert "secret-value-that-must-not-print" not in captured.err
    assert "copied private document text" not in captured.err


def test_check_lora_dataset_accepts_valid_split_dataset() -> None:
    path = _tmp_dir() / "dataset.json"
    path.write_text(
        json.dumps(
            {
                "train": [_example("lora_001")],
                "validation": [_example("lora_002")],
                "test": [_example("lora_003")],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert check_lora_dataset(path) == []


def test_check_lora_dataset_optional_missing_input_skips(capsys) -> None:  # noqa: ANN001
    missing = _tmp_dir() / "missing.json"

    exit_code = main(["--input", str(missing), "--optional"])

    assert exit_code == 0
    assert "SKIPPED" in capsys.readouterr().out
