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
