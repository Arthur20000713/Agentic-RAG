from __future__ import annotations

from backend.app.evaluation.report_diff import compare_eval_reports, render_metric_delta_markdown


def test_compare_eval_reports_tracks_core_metric_deltas() -> None:
    before = {
        "metrics": {
            "pass_rate": 0.80,
            "no_answer_accuracy": 0.70,
            "source_uri_coverage": 0.90,
            "safety_pass_rate": 1.0,
            "failure_categories": {},
            "mapping_warning_counts": {},
        }
    }
    after = {
        "metrics": {
            "pass_rate": 0.85,
            "no_answer_accuracy": 0.60,
            "source_uri_coverage": 0.95,
            "safety_pass_rate": 0.99,
            "failure_categories": {},
            "mapping_warning_counts": {},
        }
    }

    deltas = compare_eval_reports(before, after)

    values = {delta.name: delta.delta for delta in deltas}
    assert values["pass_rate"] == 0.05
    assert values["no_answer_accuracy"] == -0.10
    assert values["source_uri_coverage"] == 0.05
    assert values["safety_pass_rate"] == -0.01


def test_compare_eval_reports_lists_new_failure_categories_and_warnings() -> None:
    before = {"metrics": {"failure_categories": {"NO_ANSWER_FALSE_POSITIVE": 1}, "mapping_warning_counts": {}}}
    after = {
        "metrics": {
            "failure_categories": {"NO_ANSWER_FALSE_POSITIVE": 2, "LOW_CONFIDENCE_ACCEPTED": 1},
            "mapping_warning_counts": {"RAG_LOW_CONFIDENCE_SCORE": 3},
        }
    }

    deltas = compare_eval_reports(before, after)

    assert any(delta.name == "failure_category:LOW_CONFIDENCE_ACCEPTED" and delta.after == 1 for delta in deltas)
    assert any(delta.name == "mapping_warning:RAG_LOW_CONFIDENCE_SCORE" and delta.after == 3 for delta in deltas)


def test_render_metric_delta_markdown_outputs_table() -> None:
    before = {"metrics": {"pass_rate": 0.80}}
    after = {"metrics": {"pass_rate": 0.85}}

    markdown = render_metric_delta_markdown(compare_eval_reports(before, after))

    assert markdown.startswith("# Eval Report Delta")
    assert "| pass_rate | 0.8000 | 0.8500 | +0.0500 |" in markdown
