from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_p7.py"
SPEC = importlib.util.spec_from_file_location("benchmark_p7", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_percentile_interpolates_sorted_values() -> None:
    assert MODULE.percentile([40.0, 10.0, 30.0, 20.0], 0.5) == 25.0
    assert MODULE.percentile([10.0], 0.95) == 10.0
    assert MODULE.percentile([], 0.95) == 0.0


def test_summary_counts_http_and_transport_errors() -> None:
    samples = [
        MODULE.Sample(10.0, 200),
        MODULE.Sample(20.0, 503, "http"),
        MODULE.Sample(30.0, 0, "TimeoutError"),
    ]

    summary = MODULE.summarize(samples, 3.0)

    assert summary["requests"] == 3
    assert summary["errors"] == 2
    assert summary["errorRate"] == 2 / 3
    assert summary["throughputRps"] == 1.0
    assert summary["latencyMs"]["p50"] == 20.0
    assert summary["statusCounts"] == {"0": 1, "200": 1, "503": 1}
    assert summary["errorCounts"] == {"TimeoutError": 1, "http": 1}
