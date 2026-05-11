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
