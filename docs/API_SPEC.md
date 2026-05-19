# API Spec

All API endpoints return the unified envelope:

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "req_xxx"
}
```

Error codes are defined in `backend/app/core/errors.py`.

Current endpoints:

- `POST /api/chat`: runs the Agent workflow and returns `intent`, `answer`, `sources`, `tools_used`, follow-up state, and errors.
- `POST /api/documents/upload`: stores the uploaded file and creates a RAG ingestion task; it does not parse or index the document in this app.
- `GET /api/tasks/{task_id}`: reads an ingestion task.
- `POST /api/tasks/{task_id}/index`: synchronously proxies to the RAG-SERVER CLI ingestion gateway.
- `POST /api/measurement/analyze`: runs body-measurement analysis and returns the structured report.
- `GET /api/rag/status`: returns RAG mode, effective mode, path status, MCP availability, default collection, and last RAG error.
- `GET /api/rag/collections`: calls `RagServerClient.list_collections`; fake mode returns fake collections, while real/smoke mode with missing `RAG_SERVER_PATH` returns a unified `RAG_SERVER_UNAVAILABLE` response and does not silently fall back to fake.
- `GET /api/rag/collections/{collection}/documents/{doc_id}/summary`: calls `RagServerClient.get_document_summary`; the route requires the collection path segment and real/smoke mode with missing `RAG_SERVER_PATH` returns `RAG_SERVER_UNAVAILABLE` without using fake data.
- `GET /api/traces/{request_id}`: returns the trace bundle for a request. V2.2-B2 includes persisted `agent_trace`; `tool_trace`, `rag_trace`, `safety_result`, and `verifier_result` are reserved in the response shape for later trace panel stages.

RAG answer rules:

- Citations can only come from `RagSearchResult.citations`.
- Empty, low-confidence, or failed RAG results must not fabricate sources.
- RAG failures must clearly say the system cannot answer from retrieved evidence.

V5 chat/debug additions:

- When V3 graph execution is enabled, `POST /api/chat` can include `v3_debug.model_fallbacks`.
- `model_fallbacks` records local-model fallback events such as schema validation failure, selected model, route mode, and fallback reason.
- Local-model takeover is limited to low-risk structured tasks. API responses must not expose local-model final answers for high-risk disease, prescription, dosage, withdrawal-period, or definitive-diagnosis requests.
- No V5 endpoint performs multi-user authorization, internet deployment management, backup/restore, or production monitoring.
