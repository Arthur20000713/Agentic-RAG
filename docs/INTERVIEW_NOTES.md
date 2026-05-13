# V2 面试讲解稿

## 一句话介绍

这个项目把已有 RAG-SERVER 包装成畜牧业应用层智能助手：底层 RAG 负责知识检索，本项目负责 Multi-agent 编排、业务工具、安全校验、trace、评测和可演示前端。

## 架构讲法

1. FastAPI 提供 `/api/chat`、`/api/measurement/analyze`、`/api/rag/status`、trace API 和静态 `/app` 前端。
2. RAG-SERVER 作为 sibling 项目存在，本项目通过 MCP stdio 调用 `query_knowledge_hub`、`list_collections`、`get_document_summary`。
3. Multi-agent graph 按固定节点运行：Supervisor 路由，Specialist Agent 执行业务，Verifier 检查证据，Safety 兜底，Response 统一渲染。
4. SQLite 保存业务日志、RAG trace、agent trace、session context 和 eval run log。
5. 评测分三层：fake regression 保证稳定性，real RAG optional eval 验证真实检索质量，multi-agent eval 统计 route/path/safety/trace 指标。

## 已完成的 V2 重点

- V2.1：固化真实 RAG 接入、RAG status API、标准输出 schema、`source_uri`、trace、timeout/fallback、real eval 和失败类别。
- V2.2：实现 Supervisor、RAG、Disease、Measurement、Verifier、Safety、Response agent，并串联三条业务图。
- V2.3：实现无需 Swagger 的静态前端，覆盖 Chat、Measurement、Sources、Tools 和 Debug JSON。
- V2.4：实现 session context、slot source、TTL/stale、多轮疾病追问续接和上下文重置。
- V2.5：补齐 eval run log、真实 RAG 失败分析和 multi-agent eval。

## 演示顺序

1. 打开 `/app`，先问畜牧业知识问题，展示 answer、sources、tools 和 debug JSON。
2. 输入信息不足的疾病问题，展示最多 3 个追问和 session context 续接。
3. 输入高风险疾病问题，展示风险判断、证据引用和安全边界。
4. 切到体尺页，输入当前体尺和历史记录，展示异常项、证据和报告。
5. 打开 `/docs` 或 trace API，展示 RAG/Agent trace 可以定位每个节点。

## 真实 RAG 限制

- 默认回归不启动真实 RAG-SERVER，避免依赖 API key、外部模型、向量库状态和本机环境。
- 真实 RAG 必须显式配置 `RAG_SERVER_PATH`，并优先使用 RAG-SERVER 自己的 Python 环境。
- real eval 的 skipped report 不是 fake 替代，而是明确记录未配置原因。
- 真实质量瓶颈通过 `failure_analysis.md` 分类：无 collection、无检索结果、低分、映射问题、无证据 claim、安全问题、timeout、RAG-SERVER 不可用。

## 可强调的工程取舍

- 没有重写 RAG-SERVER，避免把 parser、embedding、BM25、rerank 等复杂能力复制到应用层。
- Multi-agent 是固定图，不做多个 agent 自由聊天，保证路径可测试、可 trace。
- fake 和 real 严格分离，fake 只做回归，real 才说明真实检索质量。
- 安全规则是硬边界，尤其是诊断、药物剂量和处方类输出。
