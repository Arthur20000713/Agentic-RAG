from __future__ import annotations

import sys

from backend.app.core.config import Settings
from backend.app.services.runtime_doctor import RuntimeDoctor


def test_runtime_doctor_reports_v3_shadow_main_path() -> None:
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": ".",
            "python_executable": sys.executable,
            "collection": "livestock_v4_2",
            "strict_real_mode": True,
        },
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": True, "allow_low_risk_takeover": False},
        local_model={"enabled": False, "allow_final_answer": False},
    )

    report = RuntimeDoctor(settings).check()

    assert report["checks"]["v3_shadow_path"]["status"] == "passed"
    assert report["checks"]["v3_shadow_path"]["v3_enabled"] is True
    assert report["checks"]["v3_shadow_path"]["model_router_shadow_mode"] is True
    assert report["checks"]["v3_shadow_path"]["local_model_takeover_enabled"] is False
