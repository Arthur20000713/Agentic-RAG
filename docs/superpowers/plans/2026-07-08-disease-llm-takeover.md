# Disease LLM Takeover Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining disease consultation gaps so non-shadow `disease_llm` can drive disease understanding, RAG evidence reasoning, and observable release checks without silent fake behavior.

**Architecture:** Keep default production settings conservative: `disease_llm.enabled=false` unless the user configures a real primary LLM. When enabled with `shadow_mode=false`, validated LLM understanding may override rule slots for low-risk structured case facts, while unsafe or invalid LLM output falls back only when `allow_rule_fallback=true`. RAG evidence gate and verifier remain mandatory before reasoning takeover.

**Tech Stack:** Python, Pydantic, pytest, FastAPI service schemas, existing multi-agent workflow.

---

### Task 1: LLM Understanding Takeover

**Files:**
- Modify: `backend/app/agent/disease_agent.py`
- Modify: `backend/app/agent/disease_understanding.py`
- Test: `tests/unit/test_disease_agent.py`
- Test: `tests/unit/test_disease_understanding_agent.py`

- [x] **Step 1: Write failing tests**
  - Add a test where `disease_llm.enabled=true` and `shadow_mode=false`; the fake primary LLM returns complete disease facts while rule extraction is incomplete. Expected: `DiseaseAgent.run()` uses LLM-derived facts, does not follow up, and builds a RAG query.
  - Add a test where non-shadow LLM understanding fails schema and `allow_rule_fallback=false`. Expected: `DiseaseAgent.run()` blocks with an explicit LLM understanding error instead of silently using rule slots.

- [x] **Step 2: Run tests to verify failure**
  - Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_disease_agent.py -q`
  - Expected: new tests fail because understanding currently records only shadow/tool results and does not influence slots.

- [x] **Step 3: Implement minimal takeover**
  - Add conversion from validated `DiseaseCaseUnderstanding` to `DiseaseSlots`.
  - In `DiseaseAgent.run()`, use converted slots only when `disease_llm.enabled=true`, `shadow_mode=false`, and validation succeeds.
  - Respect `allow_rule_fallback`: if false and non-shadow understanding fails, return a safe follow-up/error state without RAG.

- [x] **Step 4: Verify**
  - Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_disease_agent.py tests\unit\test_disease_understanding_agent.py -q`

### Task 2: Disease LLM Debug Observability

**Files:**
- Modify: `backend/app/services/chat_service.py`
- Test: `tests/integration/test_api_contract.py`

- [x] **Step 1: Write failing test**
  - Add an API/debug payload test asserting `v3_debug` includes sanitized `disease_llm` diagnostics: understanding status, evidence gate status, reasoning status, and takeover applied flag when present.

- [x] **Step 2: Run test to verify failure**
  - Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_api_contract.py -q`

- [x] **Step 3: Implement minimal debug summary**
  - Summarize status/fallback/error fields only; do not expose full prompts, raw LLM responses, API keys, or complete RAG payloads.

- [x] **Step 4: Verify**
  - Run: `.venv\Scripts\python.exe -m pytest tests\integration\test_api_contract.py -q`

### Task 3: Runtime Doctor And Release Gate

**Files:**
- Modify: `backend/app/services/runtime_doctor.py`
- Modify: `scripts/check_v6.py`
- Test: `tests/unit/test_runtime_doctor.py`
- Test: `tests/integration/test_check_v6.py`

- [x] **Step 1: Write failing tests**
  - Runtime doctor must report `disease_llm_path` status. Default disabled is allowed but visible; enabled non-shadow without real primary LLM config fails.
  - `check_v6.py --stage full` must include the disease LLM gate in its JSON result.

- [x] **Step 2: Run tests to verify failure**
  - Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_runtime_doctor.py tests\integration\test_check_v6.py -q`

- [x] **Step 3: Implement minimal checks**
  - Add `disease_llm_path` summary using `FeatureFlagService`.
  - Fail only when disease LLM is enabled for takeover but `primary_llm` is disabled, mock, missing model, missing base URL, or missing API key env name.

- [x] **Step 4: Verify**
  - Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_runtime_doctor.py tests\integration\test_check_v6.py -q`

### Task 4: Documentation And Final Verification

**Files:**
- Modify: `docs/V6_RELEASE_CHECKLIST.md`
- Modify: `README.md` if the public capability summary changes

- [x] **Step 1: Fix stale release checklist text**
  - Update ModelRouter wording from shadow-only to current low-risk takeover default.
  - Document that disease LLM takeover is supported but disabled until real primary LLM credentials are configured.

- [x] **Step 2: Run final verification**
  - Run: `.venv\Scripts\python.exe -m pytest tests\unit\test_primary_llm_client.py tests\unit\test_disease_understanding_agent.py tests\unit\test_disease_agent.py tests\unit\test_disease_query_builder.py tests\unit\test_disease_evidence_gate.py tests\unit\test_disease_reasoning_agent.py tests\unit\test_verifier_agent.py tests\integration\test_agent_graph.py -q`
  - Run: `.venv\Scripts\python.exe scripts\run_eval.py --mode v3 --output-dir .tmp_tests\v3_eval_disease_llm_takeover`
  - Run: `$env:RAG_SERVER_PATH='C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER'; .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir .tmp_tests\real_eval_disease_llm_takeover`
  - Run: `.venv\Scripts\python.exe -m pytest -m "not rag_server and not local_model" -q`
  - Run: `.venv\Scripts\python.exe scripts\check_release_v6.py --output-dir .tmp_tests\v6_release_disease_llm_takeover`

- [x] **Step 3: Commit and push**
  - Commit message: `疾病问诊：补齐LLM接管和发布门禁`
  - Push to `origin/main`.
