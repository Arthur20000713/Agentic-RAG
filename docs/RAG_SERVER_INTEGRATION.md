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

