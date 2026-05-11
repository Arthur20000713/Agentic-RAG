# MCP 工具契约初稿

V1 规划的应用层工具：

- `livestock_rag_search`：调用 `RagServerClient.query`，返回标准化 hits 与 citations。
- `get_source_detail`：调用 `RagServerClient.get_document_summary`。
- `disease_risk_evaluator`：规则评估，不调用 LLM。
- `body_measurement_analyzer`：体尺规则分析，不调用 RAG-SERVER。

工具失败时必须返回明确错误，不得伪造 RAG 命中或引用。

当前实现进度：

- 已固定 4 个 V1 工具的 `input_schema`。
- 已实现 `livestock_rag_search` wrapper，错误结果保留空 hits，不伪造 citations。
- 已实现 `get_source_detail` wrapper。
- 已实现 `ToolCaller.call_with_timeout`，超时返回 `ToolResult(status="error")` 并可写入工具日志。
- 已实现 `disease_risk_evaluator`，基于规则返回 `risk_level`、`need_vet`、`need_isolation`、`missing_info`。
- 已实现 `body_measurement_analyzer`，异常结论必须带数值 evidence；无历史时不判断趋势。
