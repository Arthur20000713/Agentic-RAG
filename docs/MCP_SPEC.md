# MCP 工具契约初稿

V1 规划的应用层工具：

- `livestock_rag_search`：调用 `RagServerClient.query`，返回标准化 hits 与 citations。
- `get_source_detail`：调用 `RagServerClient.get_document_summary`。
- `disease_risk_evaluator`：规则评估，不调用 LLM。
- `body_measurement_analyzer`：体尺规则分析，不调用 RAG-SERVER。

工具失败时必须返回明确错误，不得伪造 RAG 命中或引用。

