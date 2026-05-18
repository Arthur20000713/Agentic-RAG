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
