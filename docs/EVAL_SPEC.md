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
```

Outputs:

- `reports/eval_result.json`
- `reports/eval_result.csv`
- `reports/eval_summary.md`

`scripts/check_all.py` runs `pytest -m "not rag_server"` first, then runs this fake golden-set evaluation.
