# Agentic RAG handoff

Last updated: 2026-07-10

This handoff is for the next model/developer taking over `C:\Users\DELL\PycharmProjects\PythonProject\Agentic RAG`.

## Current Git State

- Current branch: `main`
- Latest substantive code commit before this handoff file: `230b72c`
- Recent commits:
  - `230b72c` 合并：移除疾病固定槽位抽取
  - `97464aa` 疾病问诊：移除固定槽位抽取并改为动态RAG推理
  - `d8232e9` 疾病问诊：修复正常体温补充后重复追问
  - `fe35f55` 路由接管：让本地模型分析意图并由LLM生成直接回复
  - `7b71199` LLM接管：复用RAG-SERVER的DeepSeek密钥
- Local untracked file/folder: `.idea/`
  - Do not commit `.idea/` unless the user explicitly asks.
- User requirement still applies: after substantive development, commit and push.

## Project Summary

This repository is the FastAPI application layer for a livestock Agentic RAG assistant. It does not own the underlying knowledge-base engine. It integrates with the sibling project:

`C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER`

RAG-SERVER is used through MCP stdio. Treat it as read-only unless the user explicitly asks to fix RAG-SERVER. If RAG-SERVER code is modified, commit inside the RAG-SERVER git repository as well.

Main user-facing capabilities currently implemented:

- Livestock knowledge Q&A grounded in real RAG.
- Disease consultation assistance with dynamic LLM + RAG reasoning.
- Measurement/body-size report analysis.
- Intent routing through local model/router path.
- Direct-answer path for low-risk/general messages.
- Real RAG status/readiness diagnostics.
- Local Transformers model smoke path for query normalization.
- Static frontend at `/app` plus FastAPI docs at `/docs`.

## Current Runtime Configuration

From `config/settings.yaml`:

- `rag_server.query_mode = real`
- `rag_server.collection = livestock_v4_2`
- `rag_server.repo_path = C:/Users/DELL/PycharmProjects/PythonProject/RAG-SERVER`
- `rag_server.python_executable = C:/Users/DELL/PycharmProjects/PythonProject/RAG-SERVER/.venv/Scripts/python.exe`
- `primary_llm.enabled = true`
- `primary_llm.provider = deepseek`
- `primary_llm.model = deepseek-v4-flash`
- `primary_llm.api_key_env = DEEPSEEK_API_KEY`
- `disease_llm.enabled = true`
- `disease_llm.shadow_mode = false`
- `disease_llm.require_rag_evidence = true`
- `model_router.enabled = true`
- `model_router.shadow_mode = false`
- `model_router.allow_low_risk_takeover = true`
- `local_model.enabled = true`
- `local_model.provider = transformers`
- `local_model.model = Qwen/Qwen2.5-0.5B-Instruct`
- `local_model.allow_final_answer = false`

Do not print or commit API keys. `PrimaryLLMClient` resolves the key from `DEEPSEEK_API_KEY`; if missing, it can read the same key name from `RAG-SERVER\.env`.

## How To Run

From repository root:

```powershell
.\scripts\start_app.ps1 -Port 8001
```

Open:

- `http://127.0.0.1:8001/app`
- `http://127.0.0.1:8001/docs`

The script runs `scripts\doctor_v6.py` before starting Uvicorn unless `-SkipDoctor` is passed. If behavior in the browser looks stale after code changes, restart the running app process.

Useful diagnostic endpoints:

- `GET /api/health`
- `GET /api/ready`
- `GET /api/rag/status`
- `GET /api/rag/collections`
- `GET /api/traces/{request_id}`

## Current Chat Flow

High-level `/api/chat` flow:

1. `ChatService` receives the request.
2. Intent routing decides whether the request is general Q&A, disease consultation, measurement, out-of-scope, etc.
3. V3 graph path runs when enabled.
4. Low-risk direct replies can be generated through `DirectAnswerAgent` and the primary LLM.
5. RAG-backed answers use `RagAgent` and the real RAG-SERVER MCP client.
6. Disease consultations now use dynamic disease understanding plus RAG evidence, then LLM reasoning.
7. Verifier/safety/final guard still protects final output.

Important recent change: the fixed disease slot extraction path was removed. Do not reintroduce a rigid checklist-based diagnosis flow.

## Disease Consultation State After Latest Change

Removed:

- `backend/app/agent/extractor.py`
- `tests/unit/test_slot_extractor.py`
- `SlotExtractor`
- fixed `build_follow_up_questions`
- `disease_slot_router` route/tool dependency
- the old behavior where missing fixed fields such as temperature/duration/group outbreak blocked the answer

Current disease path:

- `DiseaseAgent` sets `state.extracted_slots = {}` only for backward-compatible state shape.
- `DiseaseUnderstandingAgent` asks the primary LLM for dynamic case understanding:
  - `case_summary`
  - `species`
  - `observed_signs`
  - `context_factors`
  - `explicit_user_facts`
  - `information_gaps`
  - `confidence`
  - `source_spans`
- `DiseaseQueryBuilder` builds the RAG query from the raw/normalized user query, dynamic understanding, and session context.
- `DiseaseReasoningAgent` receives `case_understanding`, `rag_query`, `disease_assessment`, `evidence_gate`, and `rag_result`.
- Follow-up questions, if any, are generated dynamically by the LLM from the specific case and retrieved evidence.
- Session memory stores dynamic understanding and evidence refs, not fixed slot tags.

Regression guard:

```powershell
rg 'backend\.app\.agent\.extractor|SlotExtractor|build_follow_up_questions|slot_extractor|disease_slot_router|extract_slots_with_router' backend config scripts -n
```

Expected result: only the negative assertion in `scripts\check_v3.py`.

## Validation Already Run After Latest Merge

These passed on `main` after merging `codex/remove-disease-slot-extraction`:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not rag_server and not local_model" -q
```

Result:

```text
474 passed, 3 deselected
```

Also passed:

```powershell
.\.venv\Scripts\python.exe scripts\check_v3.py
.\.venv\Scripts\python.exe scripts\check_v6.py
.\.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir .tmp_tests\eval_no_slots_fake_merged
.\.venv\Scripts\python.exe scripts\run_eval.py --mode v3 --output-dir .tmp_tests\eval_no_slots_v3_merged
.\.venv\Scripts\python.exe scripts\run_eval.py --mode v5 --output-dir .tmp_tests\eval_no_slots_v5_merged
```

## Common Commands

Quick product readiness:

```powershell
.\.venv\Scripts\python.exe scripts\doctor_v6.py --json
.\.venv\Scripts\python.exe scripts\check_v6.py --stage full
.\.venv\Scripts\python.exe scripts\check_release_v6.py --output-dir .tmp_tests\v6_release
```

Main non-external test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not rag_server and not local_model" -q
```

Real RAG verification:

```powershell
$env:RAG_SERVER_PATH = 'C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER'
.\.venv\Scripts\python.exe -m pytest -m rag_server
.\.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir .tmp_tests\real_eval
```

Local model smoke:

```powershell
.\.venv\Scripts\python.exe scripts\run_local_model_smoke.py --optional --output reports\local_model_v6_transformers_smoke.json
```

Start app:

```powershell
.\scripts\start_app.ps1 -Port 8001
```

## PowerShell Notes

This machine uses Windows PowerShell. Avoid Bash syntax:

- Do not use `&&`, `||`, `export`, `rm -rf`, or Bash heredocs like `python - <<'PY'`.
- Use separate commands or `$LASTEXITCODE`.
- For Python stdin scripts, use:

```powershell
@'
print("hello")
'@ | .\.venv\Scripts\python.exe -
```

- Use `-LiteralPath` for paths with spaces.
- Do not trust terminal-displayed Chinese text. Check UTF-8 with Python `repr()` if needed.
- Before stopping processes, identify exact PID/port using `Get-NetTCPConnection`.

## Known Gaps / Not Yet Public Production

V6 is locally usable, but not public-production complete:

- No multi-user auth or tenant isolation.
- No production backup/restore/alerting plan.
- No enterprise audit or operations dashboard.
- LoRA adapter inference is not enabled by default.
- Real RAG depends on sibling RAG-SERVER availability and its local data/indexes.
- Some terminal output may show Chinese mojibake in PowerShell even when files are UTF-8.

## Next Good Development Targets

If continuing productization, prioritize:

1. Browser-level manual QA after the fixed-slot removal:
   - greeting/direct answer
   - livestock Q&A
   - disease consultation with vague symptoms
   - multi-turn disease follow-up
   - out-of-scope refusal
2. Improve disease answer UX if the evidence gate blocks too often.
3. Add a regression test that simulates a vague disease question and verifies the system does not ask a fixed checklist.
4. Strengthen README encoding/refresh because PowerShell output currently displays mojibake.
5. Add operational docs for real RAG-SERVER startup, logs, and failure triage.

## Security Rules

- Never print API keys.
- Never commit `.env`, runtime DBs, vector stores, logs, `.venv`, `.deps`, `.tmp_tests`, or `.idea`.
- If modifying RAG-SERVER, first run git status in that repo and commit changes there separately.
- Do not silently fall back from real RAG to fake mode in default product paths.
