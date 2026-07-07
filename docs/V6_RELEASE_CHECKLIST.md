# V6 Release Checklist

## Status

V6 release status: usable

Last verified locally:

```powershell
.venv\Scripts\python.exe scripts\check_release_v6.py --output-dir .tmp_tests\v6_release
```

Observed result:

- `runtime_doctor`: passed
- `v6_full_check`: passed
- `local_model_smoke`: passed
- `pytest_not_rag_server`: passed
- Regression: `422 passed, 3 deselected`

Generated runtime summary:

- `.tmp_tests\v6_release\release_check_summary.json`

## Product Gates

- Default RAG mode is real.
- Default collection is `livestock_v4_2`.
- RAG quality gate evidence is present and passed.
- `/api/health` and `/api/ready` are available.
- V3 graph is enabled by default.
- ModelRouter remains in shadow mode.
- Local transformers model is enabled for structured query normalization smoke.
- Local model final-answer generation remains disabled.
- Release check outputs `usable` or `not_usable`.

## Startup

```powershell
.\scripts\start_app.ps1 -Port 8001
```

Open:

```text
http://127.0.0.1:8001/app
```

Quick diagnostics:

```powershell
.venv\Scripts\python.exe scripts\doctor_v6.py --json
```
