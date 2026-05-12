# RAG-SERVER 集成契约

当前项目只做 RAG-SERVER 接入与畜牧应用层封装。

禁止在当前项目中重新实现：

- parser / splitter
- embedding
- vector store / BM25
- hybrid retrieval / rerank
- citation generator
- RAG dashboard

路径解析优先级：

1. 环境变量 `RAG_SERVER_PATH`
2. `config/settings.yaml` 中的 `rag_server.repo_path`

真实 MCP 入口固定为：

```powershell
python -m src.mcp_server.server
```

Real smoke checks are explicit and optional:

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
py -3.11 -m pytest tests/integration/test_rag_server_mcp_client.py tests/integration/test_rag_server_cli_gateway.py -m rag_server
```

CLI 在 V1 仅用于 ingestion 代理，不从 CLI query stdout 推断 hits、score 或 citations。

当前 adapter 进度：

- `FakeRagServerClient` 是默认测试和开发路径。
- `RagServerCliGateway` 只代理 `scripts/ingest.py`。
- `RagServerMcpClient` 已实现 stdio 子进程生命周期：
  - 使用 `rag_server.python_executable` 或当前 Python 启动。
  - 固定以 RAG-SERVER repo path 作为 `cwd`。
  - 启动命令为 `python -m src.mcp_server.server`。
  - 初始化后通过 `tools/call` 调用 `query_knowledge_hub`、`list_collections`、`get_document_summary`。
  - `close()` 会终止子进程。
- 默认测试使用本地 mock MCP server，不要求真实 RAG-SERVER。
- 真实接入测试标记为 `rag_server`，未设置 `RAG_SERVER_PATH` 时跳过。

## V2.1 source_uri 规则

业务层引用、Verifier、Trace、Eval 统一使用 `source_uri` 作为来源 ID，格式固定为：

```text
rag://{collection}/{doc_id}/{chunk_id}
```

生成规则：

1. `collection` 优先取 RAG 查询请求参数或 RAG-SERVER payload 中的 collection；缺失时使用 `default`。
2. `doc_id` 优先取 `doc_id`、`document_id`、`source_id`、`metadata.doc_id`、`metadata.document_id`。
3. `chunk_id` 优先取 `chunk_id`、`id`、`metadata.chunk_id`。
4. 缺少 `doc_id` 时生成 `unknown-doc-{sha256(title|source|rank)[:12]}`。
5. 缺少 `chunk_id` 时生成 `unknown-chunk-{sha256(content|page|rank)[:12]}`。
6. 出现 fallback ID 时必须记录 `RAG_MAPPING_PARTIAL_SOURCE_URI`。

fallback `source_uri` 只能用于追踪和展示，不得伪装成高置信证据。
