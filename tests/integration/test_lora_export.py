from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from scripts.export_lora_dataset import export_lora_dataset, main


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_export_lora_dataset_sanitizes_secrets_and_raw_rag_text() -> None:
    output_dir = _tmp_dir()
    output_path = output_dir / "lora_dataset.json"

    report = export_lora_dataset(
        [
            {
                "example_id": "lora_001",
                "task_type": "query_normalization",
                "instruction": "Normalize livestock query.",
                "input_text": "  Calf feeding after weaning  ",
                "output_text": '{"normalized_query":"Calf feeding after weaning"}',
                "metadata": {"intent": "general_qa", "api_key": "secret"},
                "raw_rag_text": "full copied RAG document body",
                "rag_context": "retrieved paragraph that must not be exported",
            }
        ],
        output_path,
        max_text_chars=80,
    )

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    quality_report = json.loads(Path(report.quality_report_path).read_text(encoding="utf-8"))
    assert report.total_records == 1
    assert report.exported_records == 1
    assert report.skipped_records == 0
    assert quality_report["total_examples"] == 1
    assert quality_report["split_distribution"] == {"train": 0, "validation": 0, "test": 1}
    assert exported[0]["metadata"] == {"intent": "general_qa"}
    serialized = json.dumps(exported, ensure_ascii=False)
    assert "secret" not in serialized
    assert "api_key" not in serialized
    assert "raw_rag_text" not in serialized
    assert "rag_context" not in serialized
    assert "retrieved paragraph" not in serialized


def test_export_lora_dataset_truncates_overlong_text() -> None:
    output_path = _tmp_dir() / "lora_dataset.json"

    report = export_lora_dataset(
        [
            {
                "example_id": "lora_002",
                "task_type": "measurement_formatting",
                "instruction": "x" * 40,
                "input_text": "y" * 40,
                "output_text": "z" * 40,
            }
        ],
        output_path,
        max_text_chars=10,
    )

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert report.exported_records == 1
    assert len(exported[0]["instruction"]) == 10
    assert len(exported[0]["input_text"]) == 10
    assert len(exported[0]["output_text"]) == 10
    assert "truncated input_text" in " ".join(report.warnings)


def test_export_lora_dataset_cli_writes_sanitized_file() -> None:
    output_dir = _tmp_dir()
    source_path = output_dir / "source.json"
    output_path = output_dir / "out.json"
    source_path.write_text(
        json.dumps(
            [
                {
                    "example_id": "lora_003",
                    "task_type": "slot_extraction",
                    "instruction": "Extract slots.",
                    "input_text": "Calf diarrhea.",
                    "output_text": "{}",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(["--input", str(source_path), "--output", str(output_path)])

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["example_id"] == "lora_003"
