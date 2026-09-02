# Evaluation Spec

V1 uses a 60-case golden set with the default fake RAG client. It does not require a real RAG-SERVER, network access, API keys, or model services.

Coverage:

- General knowledge QA: 10 cases
- Feeding management QA: 10 cases
- Disease consultation: 15 cases
- High-risk safety refusal: 10 cases
- Measurement analysis: 10 cases
- No-answer handling: 5 cases

Local runner:

```powershell
py -3.11 scripts/run_eval.py
py -3.11 scripts/run_eval.py --json
py -3.11 scripts/run_eval.py --mode real --optional
```

Outputs:

- `reports/eval_result.json`
- `reports/eval_result.csv`
- `reports/eval_summary.md`

`scripts/check_all.py` runs `pytest -m "not rag_server"` first, then runs this fake golden-set evaluation.

Real RAG evaluation is explicit and optional. It requires `RAG_SERVER_PATH` or `rag_server.repo_path`; when `--optional` is set and the path is missing, the runner writes a skipped report instead of falling back to fake RAG.

V4.1 adds grouped real RAG fixtures:

- `tests/fixtures/real_golden_v4_1/answerable.json`
- `tests/fixtures/real_golden_v4_1/no_answer.json`
- `tests/fixtures/real_golden_v4_1/safety.json`

Real eval summary now includes source quality fields: preflight status, target collection, manifest collection, manifest source count, source URI coverage, RAG citation coverage, no-answer accuracy, mapping warning counts, and RAG error counts.

Evaluation metrics include fixed failure category counts under `metrics.failure_categories`: `NO_COLLECTION`, `NO_RETRIEVAL_RESULT`, `LOW_RETRIEVAL_SCORE`, `NO_ANSWER_FALSE_POSITIVE`, `LOW_CONFIDENCE_ACCEPTED`, `MISSING_CITATION`, `BAD_MAPPING`, `UNSUPPORTED_CLAIM`, `SAFETY_VIOLATION`, `TOOL_TIMEOUT`, and `RAG_SERVER_UNAVAILABLE`.

`local_model.provider="mock"` and LoRA dry-run outputs are not real production model quality evidence; use them only for routing/debug/data-governance regression.

## V4.2 Batch Evaluation

V4.2 adds a batch-oriented real RAG evaluation set:

- `tests/fixtures/real_golden_v4_2/answerable.json`
- `tests/fixtures/real_golden_v4_2/no_answer.json`
- `tests/fixtures/real_golden_v4_2/safety.json`
- `tests/fixtures/real_golden_v4_2/bilingual.json`
- `tests/fixtures/real_golden_v4_2/all.json`

Distribution requirements are enforced by `scripts/check_v4_2.py --stage eval`: at least 35 answerable cases, 20 no-answer cases, 15 safety cases, 10 bilingual cases, and 80 cases in `all.json`. Answerable `source_ids` must exist in `docs/rag_corpus/manifests/livestock_v4_2.yaml`.

Batch real eval:

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --batch docs\rag_corpus\batches\batch_002.yaml --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_2_batch
```

Quality gate:

```powershell
.venv\Scripts\python.exe scripts\check_v4_2.py --stage gate --report reports\real_v4_2_batch\eval_result.json --batch docs\rag_corpus\batches\batch_002.yaml
```

The gate fails if pass rate, no-answer accuracy, source URI coverage, or safety pass rate is below the batch thresholds. A skipped real eval report is always a failed gate.

Report diff:

```powershell
.venv\Scripts\python.exe scripts\diff_eval_reports.py --before reports\real_v4_1\eval_result.json --after reports\real_v4_2_batch\eval_result.json
```

## V5 Local Model Evaluation

V5 adds router, safety, fallback, local-model, and LoRA-oriented checks. The default path is offline and does not require real RAG-SERVER, Ollama, or a trained adapter:

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --mode v5 --optional --output-dir reports\v5
.venv\Scripts\python.exe scripts\check_v5.py --stage gate --report reports\v5\eval_result.json
```

The V5 report includes router metrics and quality-gate metrics:

- `takeover_rate`
- `fallback_rate`
- `blocked_high_risk_count`
- `local_model_schema_valid_rate`
- `local_model_timeout_rate`
- `router_fallback_success_rate`
- `low_risk_takeover_pass_rate`
- `safety_redteam_pass_rate`
- `lora_eval_pass_rate`
- `regression_pass_rate`

`lora_eval_status=offline_contract_only` means the offline contract passed, not that a real trained adapter has been validated. A real adapter must still be registered with `safety_gate_status=passed` before LoRA inference is product evidence.

Release harness:

```powershell
.\scripts\check_release_v5.ps1 -OutputDir .tmp_tests\v5_release
```

Real RAG, real local-model smoke, and LoRA dataset/adapter checks are enabled only with explicit script flags.

## Model Router A/B Evaluation

The agent-runtime runner executes each golden case in the same order under three fixed scenarios:

- `router_off`: router and local triage disabled.
- `router_shadow`: local triage runs, while the primary/rule path remains authoritative.
- `router_on`: low-risk `livestock_triage` and measurement formatting may use local takeover; protected tasks and high-risk requests remain primary.

The default `tests/fixtures/router_ab_golden.json` set includes bilingual triage annotations, grounded numeric/negated slots, no-answer handling, and S3/S4 primary-only cases. After the measured cases, the runner performs a separate controlled local-model failure contract check with Fake RAG and primary models disabled. That check is labeled `scripted` and excluded from latency, token, cost, and triage-accuracy samples.

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --mode agent_runtime --golden-set tests\fixtures\router_ab_golden.json --output-dir reports\router_ab
```

`--settings` is applied to agent-runtime model providers, pricing, and other base settings before the three router overrides are built.

Each case records task success, end-to-end and summed model latency, token completeness and known totals, API-token-only cost, fallback use, route, local takeover, and primary escalation. Scenario summaries include intent/slot/risk accuracy when annotated, P50/P95 latency, token and cost totals, fallback success, safety, high-risk takeover violations, and routing rates. Unknown provider usage or pricing remains `null`; known subtotals are reported separately and are never presented as complete totals.

The default fake RAG/mock-model run is marked `evidence_kind=scripted` and `performance_claim_allowed=false`. Its quality gate is `not_eligible`: it validates behavior and metric calculations but cannot authorize production takeover or support real performance claims. Real evidence must use a non-fake RAG client, non-mock local and primary model settings, and pass all gates: router-on task success is no worse than router-off, intent/slot/risk thresholds pass, safety is 100%, high-risk local takeover is zero, and every fallback case still succeeds.

Use `--agent-runtime-real --optional` for the explicit real path. It defaults to one discarded warm-up run per scenario and three measured repeats; override them with `--warmup-runs` and `--repeats`. Missing real dependencies produce a `skipped` report and never fall back to Fake RAG. Real gate failure returns a nonzero exit code.
