# V3 Repo Map

This file records the real repository layout for V3 development. It mirrors the current codebase instead of introducing new roots.

## Roots

| Name | Path |
|---|---|
| `PROJECT_ROOT` | `C:\Users\DELL\PycharmProjects\PythonProject\Agentic RAG` |
| `APP_ROOT` | `backend/app` |
| `TEST_ROOT` | `tests` |
| `SCRIPT_ROOT` | `scripts` |
| `CONFIG_ROOT` | `config` |
| `DOC_ROOT` | `docs` |
| `STATIC_ROOT` | `backend/app/static/frontend` |
| `DATA_ROOT` | `data` |
| `REPORT_ROOT` | `reports` |
| `RAG_SERVER_PATH` | `C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER` |

## V2 Integration Points

| Capability | Current path |
|---|---|
| FastAPI app | `backend/app/main.py` |
| Settings | `backend/app/core/config.py`, `config/settings.yaml`, `config/settings.test.yaml` |
| RAG-SERVER adapter | `backend/app/integrations/rag_server/` |
| RAG schema and `source_uri` | `backend/app/schemas/rag_server.py`, `backend/app/integrations/rag_server/mapper.py` |
| Multi-agent graph | `backend/app/agent/graph.py` |
| Agents | `backend/app/agent/` |
| Trace service and API | `backend/app/services/trace_service.py`, `backend/app/api/traces.py` |
| Session context | `backend/app/services/session_context_service.py` |
| Evaluation runners | `backend/app/evaluation/`, `scripts/run_eval.py` |
| Static frontend | `backend/app/static/frontend/` |

## V3 Placement Rules

- Keep tests under `tests/`; do not create `backend/tests`.
- Keep settings under `config/`; do not create `configs/` as a primary config root.
- Extend the existing FastAPI app; do not create a second app entry.
- Extend existing RAG-SERVER adapters; do not reimplement parser, splitter, embedding, vector store, BM25, rerank, or citation generation.
- Use `.venv\Scripts\python.exe` for local commands.
- Keep real RAG checks explicit through `RAG_SERVER_PATH`; do not silently fall back to fake RAG.

## Baseline Commands

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server"
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports\fake
.venv\Scripts\python.exe scripts\run_eval.py --mode multi_agent --output-dir reports\multi_agent
.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
```
