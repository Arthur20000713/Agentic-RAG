# V5 Completion Report

## Scope

V5 turns the project into a local-first Agentic RAG application layer:

- Real local-model backend abstraction and Ollama-compatible client path.
- Controlled `ModelRouter` takeover for low-risk structured tasks.
- Observable fallback when local-model output is invalid, times out, or requests fallback.
- LoRA dataset governance, training command orchestration, registry metadata, offline evaluation, and guarded inference selection.
- V5 model quality gate, safety red-team evaluation, release harness, runbook, and configuration template.

## Completed Capabilities

### Real local model integration

- `LocalModelSettings` includes provider, endpoint, model, timeout, retry, and final-answer guard fields.
- `LocalModelClient` can call real local backends and still supports mock only for tests.
- `scripts/run_local_model_smoke.py` can run optional or required smoke checks.
- `local_model.allow_final_answer=false` remains the default safety posture.

### ModelRouter takeover

- Low-risk task takeover is available for query normalization, structured extraction, measurement analysis, and summarization.
- High-risk safety levels, final-answer requests, dosage, prescription, withdrawal-period, and definitive diagnosis stay on the primary guarded path.
- Route decisions and fallback data are persisted through `model_route_log` and surfaced through graph/tool/debug payloads.

### LoRA workflow

- Dataset export strips non-allowed fields and produces quality reports.
- Dataset checker validates train/validation/test split structure and sensitive-field removal.
- Training orchestration can dry-run or execute a configured training command outside the repo.
- Registry entries track base model, dataset hash, eval report path, metrics, and safety gate status.
- Inference selection only uses active adapters with `safety_gate_status=passed`.

### Evaluation and release

- `scripts/run_eval.py --mode v5` writes router and model-quality metrics.
- `scripts/check_v5.py --stage gate` evaluates the V5 quality gate.
- `tests/fixtures/v5_safety_redteam.json` covers high-risk blocking.
- `scripts/check_release_v5.ps1` runs the default offline release harness and requires explicit flags for real dependencies.

## Verification Snapshot

Latest V5.4-A2 default release harness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check_release_v5.ps1 -OutputDir .tmp_tests\v5_release_a2
```

Result: passed.

The harness completed:

- `scripts/check_v5.py --stage full`
- `pytest -m "not rag_server and not local_model" -q`
- `scripts/check_v2.py --offline --frontend-contract --docs`
- `scripts/check_v3.py --stage full`
- `scripts/check_v4_2.py --stage full`
- `scripts/run_eval.py --mode v5 --optional`
- `scripts/check_v5.py --stage gate`

## Product Boundaries

V5 does not include:

- Multi-user authentication or permission isolation.
- Internet or LAN production deployment hardening.
- Production backup/restore.
- Monitoring, alerting, or incident response.
- Enterprise audit controls.

Real local model and LoRA adapter acceptance still require the user to provide the local model service, trained adapter, and any external training environment. Offline skipped or contract-only reports are useful engineering checks, not product evidence for those external assets.
