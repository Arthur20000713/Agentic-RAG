# Codex Memory: RAG-SERVER

This file records a read-only analysis of `C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER` for future Codex work in this workspace.

## Project Purpose

`RAG-SERVER` is a modular RAG knowledge-base service. It connects document ingestion, hybrid retrieval, reranking, multimodal image handling, evaluation, and observability into one pipeline, then exposes query capabilities through MCP for MCP-compatible clients.

It is not a conventional HTTP API service. No FastAPI/Flask routes were found. Main external entry points are:

- MCP stdio service: `src/mcp_server/server.py`
- Streamlit Dashboard: `src/observability/dashboard/app.py`
- CLI scripts: `scripts/ingest.py`, `scripts/query.py`, `scripts/evaluate.py`
- Package console entry in `pyproject.toml`: `mcp-server = "main:main"`, but current `main.py` only loads config and prints a Phase E message. It does not start the real MCP server.

## Architecture

Core data flow:

1. Ingest documents: PDF to `Document`
2. Split documents: `Document` to `Chunk`
3. Transform/enrich chunks: chunk refine, metadata enrich, image caption
4. Encode chunks: dense embedding plus sparse/BM25 stats
5. Persist data: ChromaDB, BM25 index, image index, ingestion history
6. Query: query processing, dense retrieval, sparse retrieval, RRF fusion, optional rerank
7. Build response: citations plus multimodal MCP content
8. Observe: query/ingestion traces written to `logs/traces.jsonl`
9. Evaluate: golden set plus custom/ragas/composite evaluator

Important contracts:

- `src/core/types.py`: `Document`, `Chunk`, `ChunkRecord`, `ProcessedQuery`, `RetrievalResult`
- `src/core/settings.py`: settings dataclasses, config loading, repo-relative path resolution
- `src/libs/*/base_*.py`: abstractions for LLM, embedding, vector store, loader, splitter, reranker, evaluator

## Main Modules

### Core

- `src/core/settings.py`
  - Default config path: `config/settings.yaml`
  - `REPO_ROOT` is derived from source location, reducing dependence on current working directory
  - `resolve_path()` resolves repo-relative paths to absolute paths
- `src/core/types.py`
  - Shared data contracts across the pipeline
  - `Document`/`Chunk`/`ChunkRecord` metadata should include `source_path`
- `src/core/query_engine/`
  - `query_processor.py`: query normalization, keyword extraction, filter parsing
  - `dense_retriever.py`: embeds query and searches vector store
  - `sparse_retriever.py`: BM25 retrieval plus vector-store lookup for text/metadata
  - `fusion.py`: RRF fusion
  - `hybrid_search.py`: orchestrates dense, sparse, and fusion
  - `reranker.py`: rerank wrapper with fallback behavior
- `src/core/response/`
  - `response_builder.py`: builds MCP responses
  - `citation_generator.py`: generates source citations
  - `multimodal_assembler.py`: resolves image references and creates MCP image content
- `src/core/trace/`
  - `TraceContext`: records stages, durations, metadata
  - `TraceCollector`: default output is `logs/traces.jsonl`

### Ingestion

- `src/ingestion/pipeline.py`
  - Six-stage ingestion: integrity, load, split, transform, embed, upsert
  - Defaults to PDF processing through `PdfLoader`
  - Uses SHA256 and `data/db/ingestion_history.db` for idempotent skipping
- `src/ingestion/document_manager.py`
  - Coordinates document lifecycle across ChromaDB, BM25, image storage, and integrity DB
  - Supports list, detail, delete, and stats operations
- `src/ingestion/chunking/document_chunker.py`
  - Wraps the splitter implementation
- `src/ingestion/transform/`
  - `chunk_refiner.py`: rule-based or LLM chunk refinement
  - `metadata_enricher.py`: rule-based or LLM metadata enrichment
  - `image_captioner.py`: vision LLM image captions
- `src/ingestion/embedding/`
  - `dense_encoder.py`, `sparse_encoder.py`, `batch_processor.py`
- `src/ingestion/storage/`
  - `vector_upserter.py`: writes ChromaDB records
  - `bm25_indexer.py`: writes BM25 JSON index
  - `image_storage.py`: stores image files and SQLite image index

### Libs

Pluggable backends live under `src/libs/`:

- `src/libs/llm/`: OpenAI, Azure, DeepSeek, Ollama text LLMs; OpenAI/Azure vision LLMs; `LLMFactory`
- `src/libs/embedding/`: OpenAI, Azure, Ollama, `LocalHashEmbedding`; `EmbeddingFactory`
- `src/libs/vector_store/`: ChromaDB; `VectorStoreFactory`
- `src/libs/splitter/`: recursive splitter; `SplitterFactory`
- `src/libs/reranker/`: none, CrossEncoder, LLM reranker; `RerankerFactory`
- `src/libs/evaluator/`: none, custom, ragas, composite; `EvaluatorFactory`
- `src/libs/loader/`: `BaseLoader`, `PdfLoader`, `SQLiteIntegrityChecker`

## MCP Server

Real MCP service entry:

- `src/mcp_server/server.py`
  - Uses stdio transport
  - Keeps stdout reserved for JSON-RPC; logs must go to stderr
  - Preloads heavy dependencies such as ChromaDB to avoid worker-thread import lock issues
- `src/mcp_server/protocol_handler.py`
  - Uses `mcp.server.lowlevel.Server`
  - Registers `tools/list` and `tools/call`
  - Registers three default tools

Default MCP tools:

1. `query_knowledge_hub`
   - File: `src/mcp_server/tools/query_knowledge_hub.py`
   - Parameters:
     - `query`: string, required
     - `top_k`: integer, optional, default `5`, range `1` to `20`
     - `collection`: string, optional
   - Behavior: runs `HybridSearch`, optionally reranks, returns text and optional image MCP content
   - Return: `CallToolResult` with `TextContent`/`ImageContent`; errors use `isError=true`

2. `list_collections`
   - File: `src/mcp_server/tools/list_collections.py`
   - Parameters:
     - `include_stats`: boolean, optional, default `true`
   - Behavior: lists ChromaDB collections
   - Return: Markdown text list

3. `get_document_summary`
   - File: `src/mcp_server/tools/get_document_summary.py`
   - Parameters:
     - `doc_id`: string, required
     - `collection`: string, optional
   - Behavior: looks up ChromaDB chunks by `source_ref` or chunk id, then generates title, summary, tags, source, and chunk count
   - Return: Markdown document summary; missing document returns `isError=true`

Authentication notes:

- MCP stdio has no application-level authentication in this project.
- Model provider authentication is configured through `config/settings.yaml`.

## Dashboard

Entry points:

- `src/observability/dashboard/app.py`
- `scripts/start_dashboard.py`
- `scripts/start_dashboard_local.ps1`

Pages:

- Overview: `src/observability/dashboard/pages/overview.py`
- Data Browser: `src/observability/dashboard/pages/data_browser.py`
- Ingestion Manager: `src/observability/dashboard/pages/ingestion_manager.py`
- Ingestion Traces: `src/observability/dashboard/pages/ingestion_traces.py`
- Query Traces: `src/observability/dashboard/pages/query_traces.py`
- Evaluation Panel: `src/observability/dashboard/pages/evaluation_panel.py`

The Dashboard has no built-in login/auth. Data Browser and Ingestion Manager may delete or re-ingest data, so treat UI changes there as operationally sensitive.

## CLI And Service Entry Points

### MCP stdio

Recommended actual server command:

```bash
python -m src.mcp_server.server
```

Do not assume `mcp-server` starts the MCP server until `pyproject.toml` and `main.py` are fixed.

### Document Ingestion

File: `scripts/ingest.py`

```bash
python scripts/ingest.py --path <file-or-dir> --collection <name> --force --config config/settings.yaml --verbose --dry-run
```

Parameters:

- `--path/-p`: required; file or directory; directories are recursively scanned for PDFs
- `--collection/-c`: default `default`
- `--force/-f`: force re-ingestion, ignoring ingestion history
- `--config`: default `config/settings.yaml`
- `--verbose/-v`
- `--dry-run`

Exit codes:

- `0`: all succeeded
- `1`: partial failure
- `2`: all failed or config error

### Query

File: `scripts/query.py`

```bash
python scripts/query.py --query "..." --collection default --top-k 10 --no-rerank --verbose
```

Parameters:

- `--query/-q`: required
- `--collection/-c`: default `default`
- `--top-k`: default `10`
- `--config`: default `config/settings.yaml`
- `--no-rerank`
- `--verbose`

Exit codes:

- `0`: success
- `1`: query failure
- `2`: config/init failure

### Evaluation

File: `scripts/evaluate.py`

```bash
python scripts/evaluate.py --test-set tests/fixtures/golden_test_set.json --collection default --top-k 10 --json --no-search
```

Parameters:

- `--test-set`: default `tests/fixtures/golden_test_set.json`
- `--collection`
- `--top-k`: default `10`
- `--json`
- `--no-search`

Exit codes:

- `0`: success
- `1`: evaluation failure
- `2`: config error

### Dashboard

```bash
python scripts/start_dashboard.py --port 8501 --host localhost
```

Windows local wrapper:

```powershell
.\scripts\start_dashboard_local.ps1 -Port 8501 -HostName localhost
```

## Configuration, Dependencies, Data

Main config file:

- `config/settings.yaml`

Main config sections:

- `llm`: provider, model, deployment name, Azure endpoint/API version, API key, temperature, max tokens
- `embedding`: provider, model, dimensions, API key, Azure endpoint/deployment/version, base URL
- `vision_llm`: enabled, provider, model, max image size
- `vector_store`: provider, Chroma persist directory, collection name
- `retrieval`: dense top k, sparse top k, fusion top k, RRF k
- `rerank`: enabled, provider, model, top k
- `evaluation`: enabled, provider, metrics
- `observability`: log level, trace enabled, trace file, structured logging
- `ingestion`: chunk size, chunk overlap, splitter, batch size, chunk refiner, metadata enricher

Security note:

- The scanned `config/settings.yaml` appears to contain a real API key. Do not copy that value into docs, commits, logs, prompts, or generated artifacts. Prefer replacing it with a placeholder/env-var based loading path and rotate the key.

Key dependencies from `pyproject.toml`:

- Python `>=3.10`
- `pyyaml`
- `langchain-text-splitters`
- `chromadb`
- `mcp`
- `jieba`
- `markitdown[pdf]`
- `streamlit`
- `ragas`
- `datasets`

Development dependencies:

- `pytest`
- `pytest-cov`
- `pytest-asyncio`
- `pytest-mock`
- `ruff`
- `mypy`
- `openai`

Local wrapper scripts additionally depend on fixed machine-local Python paths and `.deps`:

- `scripts/run_local.ps1`
- `scripts/start_dashboard_local.ps1`

Environment variables:

- Source code mainly reads API keys/endpoints/base URLs from `settings.yaml`.
- No unified `.env` or environment-variable injection layer was found.
- PowerShell wrappers set `PYTHONPATH` and `PATH`.

Data directories:

- ChromaDB: `data/db/chroma`
- BM25: `data/db/bm25/<collection>`
- Image files: `data/images/<collection>`
- Image index: `data/db/image_index.db`
- Ingestion history: `data/db/ingestion_history.db`
- Traces: `logs/traces.jsonl`
- Test data: `tests/fixtures/`

## Extension Guide

### Add An LLM Provider

- Implement `src/libs/llm/base_llm.py` `BaseLLM`
- Implement `chat()`
- Register it in the LLM factory/export path
- Update `config/settings.yaml` `llm.provider`

### Add An Embedding Provider

- Implement `src/libs/embedding/base_embedding.py` `BaseEmbedding`
- Implement `embed()` and `get_dimension()`
- Register it in `EmbeddingFactory`
- Add tests similar to `tests/unit/test_embedding_factory.py`

### Add A Vector Store

- Implement `src/libs/vector_store/base_vector_store.py`
- Required methods: `upsert()`, `query()`
- Strongly recommended methods: `delete()`, `clear()`, `get_by_ids()`
- Register it in `VectorStoreFactory`
- Verify sparse retrieval and `DocumentManager` behavior, because they may rely on lookup/delete capabilities

### Add A Loader

- Implement `src/libs/loader/base_loader.py`
- Return standard `Document`
- Ensure metadata includes `source_path`
- If supporting images, follow the existing `Document.metadata["images"]` convention

### Add A Splitter

- Implement `src/libs/splitter/base_splitter.py`
- Implement `split_text()`
- Register it in `SplitterFactory`
- Update `ingestion.splitter`

### Add A Reranker

- Implement `src/libs/reranker/base_reranker.py`
- Implement `rerank(query, candidates, trace, **kwargs)`
- Preserve fallback behavior so reranker failure does not break the full query path

### Add An Evaluator

- Implement `src/libs/evaluator/base_evaluator.py`
- Implement `evaluate()`
- Register it in `EvaluatorFactory`
- Validate with `tests/fixtures/golden_test_set.json`

### Add An MCP Tool

- Create a module under `src/mcp_server/tools/`
- Provide `TOOL_NAME`, `TOOL_DESCRIPTION`, `TOOL_INPUT_SCHEMA`
- Implement an async handler returning `mcp.types.CallToolResult`
- Register it in `_register_default_tools()` in `src/mcp_server/protocol_handler.py`

### Add A Dashboard Page

- Add a page module under `src/observability/dashboard/pages/`
- Provide a `render()` function
- Add it to `st.Page` registration in `src/observability/dashboard/app.py`
- Put complex data access in `src/observability/dashboard/services/`

## Project Patterns To Preserve

- Use `Settings` plus factory patterns for backend selection.
- Avoid hardcoding providers inside business logic.
- Use shared contracts from `src/core/types.py` for cross-module data.
- Use `resolve_path()` or repo-relative paths instead of relying on process working directory.
- Keep retrieval robust: dense, sparse, and rerank failures should degrade where possible.
- In MCP stdio code, stdout is for JSON-RPC only; logs must go to stderr.
- Ingestion writes multiple stores, so consider consistency across ChromaDB, BM25, image storage, and integrity DB.
- When adding persistent data, update Dashboard views, `DocumentManager`, and cleanup logic.
- Text/metadata may contain Chinese; be careful with UTF-8 on Windows terminals.

## Risks And Known Issues

- `main.py` is not the actual MCP server entry, but `pyproject.toml` maps the `mcp-server` console script to it.
- `config/settings.yaml` appears to contain a real API key. Treat it as sensitive and do not reproduce it.
- `README.md` shows encoding artifacts, suggesting documentation encoding or read/display mode issues.
- The scanned project may have uncommitted changes. Before editing there, check status and avoid overwriting user work.
- Dashboard has no auth; do not expose it to untrusted networks without adding protection.
- ChromaDB, BM25, and SQLite writes are not wrapped in one transaction; interrupted ingestion can leave partial writes.
- `scripts/run_local.ps1` and `scripts/start_dashboard_local.ps1` contain machine-specific Python paths.
- Ragas, CrossEncoder, and external LLM tests may require network/API/model downloads; avoid making them part of default quick validation.
- `.deps`, `.venv`, `.tmp`, `data`, and `logs` are generated/runtime directories, not source.

## Test And Verification Commands

Useful lightweight checks:

```bash
python -m pytest tests/unit
python -m pytest tests/integration -m "not llm"
python -m pytest tests/e2e -m "not llm"
python -m ruff check src tests scripts
python -m mypy src
```

Functional validation suggestions:

1. Config loading: run `tests/unit/test_config_loading.py`
2. Provider factories: run `tests/unit/test_embedding_factory.py`, `tests/unit/test_llm_factory.py`, `tests/unit/test_vector_store_contract.py`
3. Ingestion: run `scripts/ingest.py --dry-run` before real ingestion on a small PDF
4. Query: after ingestion, run `scripts/query.py --verbose` to inspect dense/sparse/fusion/rerank stages
5. MCP: run `tests/integration/test_mcp_server.py` and `tests/e2e/test_mcp_client.py`
6. Dashboard: run `scripts/start_dashboard.py` and inspect Overview, Data Browser, Trace, and Evaluation pages
7. Evaluation: run `scripts/evaluate.py --no-search` first, then run golden-set evaluation against a real collection

## Analysis Scope

The subagent performed read-only analysis of these main paths:

- `README.md`
- `pyproject.toml`
- `main.py`
- `config/settings.yaml`
- `src/core/`
- `src/ingestion/`
- `src/libs/`
- `src/mcp_server/`
- `src/observability/`
- `scripts/`
- `tests/`

No commands that modify data, indexes, logs, or caches were intentionally run during analysis.
