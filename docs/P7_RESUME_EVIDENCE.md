# P7 双版本简历证据

本文把候选简历表述映射到当前源码、测试、报告和演示步骤。当前状态是 `codex/java-enterprise-integration` 工作树已实现并本机验证；在形成可审查提交前，不使用“已发布/已交付到生产”等措辞。

## 1. 共同项目定义

**畜牧业 Agentic RAG 企业智能助手**｜个人项目｜Python AI + Java 业务系统

背景：面向畜牧业知识问答、疾病辅助问诊、文档索引与体尺分析，将既有 RAG/Agent 能力接入具备身份、数据、事务、审计和稳定性约束的企业业务入口。

边界：Java 是客户端唯一入口和业务事实源；Python 负责 AI 计算；底层 embedding、BM25、rerank 属于 sibling `RAG-SERVER`，不能写成本仓库独立实现。

## 2. AI 应用岗版本

### 可用简历表述

- 设计 LangGraph 条件图编排 Supervisor、RAG、动态病例理解、Grounded Answer、Verifier、Safety 与 Response 节点，输出 intent、risk、evidence、citation 和 toolsUsed，使 Agent 路径可追踪、可测试。
- 通过 MCP stdio 接入 sibling RAG-SERVER，并将检索结果映射为稳定 `sourceUri`；建立低置信度空引用、证据门和安全拒答约束，避免检索失败或证据不足时编造来源。
- 构建动态问诊理解、information gaps、RAG query builder 与条目级 evidence reasoning，替代固定槽位清单；以有界历史和版本化 opaque context 支持多轮续接。
- 建立 fake、real RAG、Agent 路由与安全分层评测，结合模型 schema 校验/fallback、runtime doctor 和发布门禁区分稳定回归与真实依赖质量。
- 将 Python AI 能力封装为 `/internal/v1` HTTP 服务，由 Java 统一完成鉴权、会话、任务和审计；本机 stub 压测 20 个独立会话持续 5 分钟，4,932 请求 0 错误，p95 1.684 秒。

最后一条性能必须保留“本机 stub/fake RAG”限定，不能改写为真实模型性能。

### 证据矩阵

| 声明 | 源码 | 测试 | 报告 / 演示 | 状态与限制 |
| --- | --- | --- | --- | --- |
| LangGraph 条件图与工具链 | `backend/app/agent/langgraph_workflow.py`、`graph.py`、`state.py` | `test_langgraph_workflow.py`、`test_agent_graph.py` | P7.2 浏览器、`DEMO_SCRIPT.md` §2.1 | 当前强证据；一次工具链不等于所有请求固定路径 |
| citation/source URI 与保守回答 | `mcp_stdio_client.py`、`mapper.py`、`grounded_answer_agent.py`、`verifier_agent.py` | RAG client、grounded answer、verifier tests | P5/P7 reports | 机制已实现；P7 没有重跑当前 real quality gate |
| 动态疾病理解 | `disease_understanding.py`、`disease_query_builder.py`、`disease_evidence_gate.py`、`disease_reasoning.py` | 对应 unit/e2e | `DEMO_SCRIPT.md` §2.2 | 当前强证据；禁止再写固定槽位抽取 |
| 低置信度与 Safety | `rag_answer_policy.py`、`safety_agent.py`、`safety.py` | `P5AiChatOrchestrationIntegrationTest`、`test_disease_consultation_flow.py` | P5 report | 当前回归证据；默认 fake UI 不动态覆盖全部 fixture |
| 模型路由与 fallback | `backend/app/model/router.py`、`local_backends.py` | router/fallback unit/e2e | V5 reports | 机制已实现；LoRA 不是已部署推理，local model 不生成最终答案 |
| 分层评测 | `backend/app/evaluation/`、`scripts/run_eval.py` | eval/safety tests | 历史 eval reports | 可写“构建评测体系”；不能写当前 real 80/80 |
| Java HTTP 集成 | `internal_v1.py`、`internal_ai_service.py`、Java `PythonAi*Client` | contract、P5/P6 integration | P5/P6/P7 reports | 当前强证据；用户 JWT 不进入 Python |

### 面试自证追问

1. 为什么应用层不重写 embedding/BM25/rerank？阅读 `docs/RAG_SERVER_INTEGRATION.md` 与 `mcp_stdio_client.py`。
2. 低置信度为什么必须空引用？阅读 `rag_answer_policy.py`、`grounded_answer_agent.py`、`verifier_agent.py`。
3. 动态病例理解如何替代固定槽位又控制幻觉？阅读四个 disease 模块及对应 e2e。
4. 为什么业务 outcome 返回 200，而 transport failure 才进入熔断？阅读 `contracts/ai-service-v1.yaml` 与 Java chat client。
5. fake/real/Agent eval 分别证明什么、不能证明什么？阅读 `scripts/run_eval.py` 和 `docs/EVAL_SPEC.md`。

## 3. Java / 银行 / 央企研发岗版本

### 可用简历表述

- 使用 Spring Boot 构建 AI 业务统一入口，落地 JWT access/refresh rotation、RBAC、资源所有权和 Redis revoke/TTL；认证状态不可用时受保护接口 fail-closed。
- 基于 MySQL、Flyway 和 JPA 实现用户、会话、消息、任务、审计、文档与畜牧业务模型，通过唯一约束、乐观锁、状态机和事务化审计保证业务一致性。
- 设计 Java→Python `/internal/v1` 契约，以 `X-Request-ID`、`Idempotency-Key`、operation record 和 MySQL `contextVersion` 处理关联、幂等、并发冲突及响应丢失对账，避免跨服务双写。
- 对 chat 集成 timeout、circuit breaker 和 bulkhead，并为各 Python client 建立独立超时/错误映射；故障演练验证 Python 快速失败、Redis fail-closed、MySQL 不可写时 `pythonCalled=false`。
- 使用 Testcontainers、HTTP client contract test、pytest、Compose E2E、secret/image scan 与发布脚本形成交付门禁；本机 Java 127 tests、Python 611 passed/3 skipped，业务 stub 50 VU 5 分钟 p95 27.83 ms、0 错误。

最后一条必须保留“本机 stub”限定。项目没有 WireMock；不要写“Redis 实现幂等”或“全链路自动重试”。

### 证据矩阵

| 声明 | 源码 | 测试 | 报告 / 演示 | 状态与限制 |
| --- | --- | --- | --- | --- |
| JWT/RBAC/所有权 | `SecurityConfig`、`JwtService`、`RedisRefreshTokenFamilyStore`、`OwnershipGuard` | P3 security/Redis outage tests | P3 report、Demo §3.1 | 当前强证据；不是多租户平台 |
| MySQL/Flyway/乐观锁 | Flyway V1–V7、Conversation/BizTask `@Version` | Infrastructure、P4/P6 integration | P2/P4/P6 reports | 当前强证据；没有生产 HA |
| Redis 边界 | refresh family/revoke + `RedisAiContextStore` CAS | 对应 Java tests | P3/P5 reports | Redis 是认证状态和缓存，不是业务事实源或幂等权威 |
| 会话/任务/审计 | `MessageSubmissionService`、`AiQueryTransactionService`、`TaskStateMachine`、`AuditService` | P4/P5 integration | P4/P5 reports | 当前强证据；审计是应用审计，不宣称不可篡改/合规认证 |
| 跨服务幂等/对账 | 两份 OpenAPI、Java clients、Python execution repository | contract、chat/document tests | ADR-0002、P5/P6 | 当前强证据；不承诺模型计费 exactly-once |
| Resilience4j 与故障 | `PythonAiChatClient`、`AiClientConfiguration` | chat client、P7 drill | P7.1/P7.2 | chat 有 CB/bulkhead；不能泛化为所有调用自动重试 |
| 迁移与可靠索引 | 两个 migration scripts、`DocumentIndexReconciler` | P4/P6 migration/index tests | P4/P6 reports、Migration Runbook | 算法/集成已验证；未宣称真实生产迁移/真实向量入库 |
| 发布门禁与性能 | `check_release_v7.ps1`、security/benchmark scripts | Java/Python full suites | P7.2 report、Demo §4 | Windows 本机 deterministic fake RAG；不是生产 SLA |

### 面试自证追问

1. 为什么 Java 调用 Python 时不持有 MySQL 长事务？阅读 `AiQueryTransactionService` 与 ADR-0002。
2. MySQL contextVersion 与 Redis opaque context 如何避免旧缓存覆盖新状态？阅读 `RedisAiContextStore` 及其测试。
3. Redis 故障为什么必须拒绝受保护请求？阅读 `RedisRefreshTokenFamilyStore`、security integration tests。
4. 同一 operation 如何处理重放、payload 冲突和响应丢失？阅读两份 OpenAPI、Python execution repository、P5 tests。
5. MySQL 不可写时如何证明没有先调用 Python？阅读 `check_p7_resilience.ps1` 和 P7 report。

## 4. 禁止宣称

- 高可用微服务集群、银行级系统、等保/合规认证、公网生产上线或生产 SLA；
- 当前 Compose 使用真实 RAG/真实模型，或把 stub 性能写成真实 AI 性能；
- 当前 real eval 80/80；未重跑前只能按日期说明历史证据，且需处理报告冲突；
- 本仓库自研 RAG-SERVER 的 embedding、BM25、rerank；
- LoRA 已部署、local model 生成最终答案；
- WireMock、Redis 幂等、全链路自动重试、所有 AI client 均有同一 CB/bulkhead；
- 多租户隔离、审计不可篡改、已完成生产数据迁移或真实文档向量入库；
- 绝对“零漏洞/绝无 secret”。只能写指定扫描时点 0 findings、0 个已有修复版本的 HIGH/CRITICAL。

## 5. 数字引用规则

所有测试和性能数字以 `docs/reports/P7_SECURITY_PERFORMANCE_RELEASE_REPORT.md` 的 2026-08-11 本机快照为准。`.tmp_tests` 原始产物属于本地临时证据，不假设 clean clone 自带；提交态以阶段报告和最终交付报告为准。任何后续代码变更都应重新运行门禁后再更新数字。
