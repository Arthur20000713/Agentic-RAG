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

Agent Workflow 当前使用这些工具作为内部能力边界：

- 普通问答：调用 `RagServerClient.query` 后由 `AnswerGenerator` 拼装引用。
- 疾病问诊：先抽槽并追问，信息充分后调用疾病风险规则和 RAG 查询，最终经过 `FinalSafetyGuard`。
- 体尺分析：调用 `BodyMeasurementAnalyzer`，异常项必须带 evidence。

## V2.1 RAG-SERVER 标准输出字段

`query_knowledge_hub` 的业务层标准输出必须通过 `RagSearchResult` 和 `StandardRetrievedContext` 表达，不允许 Agent、Verifier 或前端直接依赖 RAG-SERVER 原始 MCP payload。

`StandardRetrievedContext` 必须包含：

- `rank`
- `collection`
- `doc_id` / `document_id`
- `chunk_id`
- `title` / `document_title`
- `content`
- `source_uri`
- `score`
- `score_type`
- `raw_score`
- `mapped_score`
- `metadata`

`RagSearchResult` 必须包含：

- `status`
- `hits`
- `citations`
- `answer_text`
- `raw_response_id`
- `mapping_warnings`
- `error_code`
- `error_message`

`source_uri` 是引用、Verifier、Trace 和 Eval 的稳定来源 ID。V2.1-A3 只固化 schema 和透传字段；缺失字段时的 fallback `source_uri` 生成规则由 V2.1-A4 实现。
