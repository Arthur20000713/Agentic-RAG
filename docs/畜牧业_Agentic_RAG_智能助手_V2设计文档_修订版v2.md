# 基于既有 RAG-SERVER 的畜牧业 Multi-agent MCP 智能助手 V2 设计文档（修订版 v2）

## 0. 文档定位

本文档基于当前 V1 已完成情况制定，用于指导 V2 阶段开发。

V1 已完成的是应用层闭环：

- FastAPI 应用骨架
- SQLite 应用数据层
- RAG-SERVER Adapter
- Fake / MCP stdio RAG client
- MCP Wrapper
- 疾病风险规则
- Safety Guard / Final Safety Guard
- 体尺分析
- 三条业务闭环：文档问答、疾病问诊、体尺报告
- API、脚本、E2E、60 条 golden set

V1 的关键变化是：

> 项目不再从零开发 RAG，而是接入既有 RAG-SERVER。V2 设计必须围绕“如何把既有 RAG-SERVER 产品级接入 Agent 系统”展开。

因此，V2 不重复建设向量库、切片、embedding、BM25 等 RAG 底层能力，而重点升级：

1. 真实 RAG-SERVER 产品级验收
2. RAG-SERVER MCP 契约固化
3. RAG trace、tool trace、agent trace
4. Real RAG eval 与 failure analysis
5. Supervisor + Specialist Agents 的可控 Multi-agent Workflow
6. Session Context 多轮追问增强
7. 前端可演示闭环
8. V2 Harness 与 Code Agent 开发约束

---

# 1. V1 真实基线

## 1.1 V1 已完成能力

当前 V1 已经完成以下基础能力：

| 模块 | 完成情况 |
|---|---|
| 项目骨架 | FastAPI、配置文件、统一响应、错误码、检查脚本 |
| 应用数据层 | SQLite、migrations、repository、QA log、tool call log |
| RAG 接入 | RagServerClient 抽象、Fake client、MCP stdio client、client factory |
| RAG-SERVER 工具 | query_knowledge_hub、list_collections、get_document_summary |
| MCP Wrapper | livestock_rag_search、get_source_detail、disease_risk_evaluator、body_measurement_analyzer |
| 规则与安全 | 疾病风险规则、药物剂量拦截、确定性诊断拦截、Final Safety Guard |
| 体尺分析 | 当前值、历史值、demo history 标注、异常结论数值依据 |
| Agent Workflow | general QA、disease consultation、measurement analysis 三条闭环 |
| API | /api/chat、/api/documents/upload、/api/tasks/{task_id}/index、/api/tasks/{task_id}、/api/measurement/analyze |
| 测试 | 77 passed，2 deselected |
| 评测 | 60 条 fake golden set，60/60 passed |
| 真实 RAG 验证 | MCP smoke test、CLI ingestion dry-run smoke test |

## 1.2 V1 边界与限制

V1 仍然存在以下限制：

1. 默认是 fake RAG，不是真实知识库检索。
2. 真实 RAG-SERVER 已有 adapter 和 smoke test，但缺少产品级验收。
3. 没有正式前端 UI，主要通过 Swagger、API 和脚本调试。
4. 英文问题容易被路由为 out_of_scope。
5. 会话历史和多轮上下文能力很轻量。
6. 文档上传是 ingestion proxy，不是完整用户可视化文档管理流程。
7. Safety 是规则型，不是复杂医学安全审查系统。
8. Golden set 偏确定性 fake workflow，尚未用于真实 RAG 质量调优。

## 1.3 V2 设计原则

V2 必须遵守以下原则：

1. **不重写 RAG-SERVER**：既有 RAG-SERVER 继续作为知识检索核心。
2. **强化接入契约**：固化 RAG-SERVER MCP 工具 schema、超时、错误码、降级逻辑。
3. **先真实接入，后 Multi-agent**：先完成 V2.1 的真实 RAG 接入和评测，再进入 V2.2 的 Multi-agent Workflow。
4. **不做多个 Agent 自由对话**：只做 Supervisor + Specialist Agents 的可控工作流。
5. **不把 fake eval 当真实质量证明**：fake eval 只做回归测试，real eval 才用于真实 RAG 质量验证。
6. **继续保持安全边界**：V2 仍不输出具体药物剂量，不做确定性诊断。
7. **每个阶段必须保持 V1 回归通过**：V1 fake eval、API contract、Safety tests 和三条业务闭环不得被破坏。

---

# 2. V2 分段交付计划

## 2.1 为什么拆分 V2

V2 同时涉及真实 RAG-SERVER 接入、Multi-agent、前端、Session Context、Real Eval、Trace、Verifier 和 Harness。若一次性开发，容易出现：

- V1 稳定性被破坏
- LangGraph 重构和 RAG-SERVER 接入问题混在一起
- 前端开发阻塞后端验收
- Real eval 失败时无法定位问题来源
- Code Agent / subagent 并行开发时改动范围失控

因此 V2 采用 V2.1–V2.5 分段交付。

## 2.2 V2 分段

```text
V2.1：真实 RAG-SERVER 接入 + RAG trace + real eval
V2.2：Multi-agent Workflow + Agent trace + Safety/Verifier Agent
V2.3：前端 UI + Trace Debug Panel
V2.4：Session Context 多轮追问增强
V2.5：真实评测报告、失败分析和面试材料完善
```

## 2.3 阶段依赖关系

1. **V2.1 必须先完成**，目标是将真实 RAG-SERVER 接入做稳。
2. **V2.2 依赖 V2.1**，在真实 RAG 接入稳定后再引入 Multi-agent Workflow。
3. **V2.3 可在 V2.2 后进行**，也可在 API 契约稳定后部分并行。
4. **V2.4 依赖 V2.2**，因为 Session Context 需要与 Multi-agent Workflow 对接。
5. **V2.5 贯穿全阶段**，但 real eval 的正式报告依赖 V2.1。

## 2.4 每阶段通用回归要求

每个 V2 子阶段完成后，必须保证：

```text
1. pytest tests/ 全部通过。
2. fake golden-set eval 继续通过。
3. API contract 不破坏统一响应格式。
4. Safety tests 继续通过。
5. 三条 V1 业务闭环继续可用。
6. 未配置 RAG_SERVER_PATH 时，默认本地检查不失败。
```

---

# 3. V2 总体架构

## 3.1 V2 架构图

```text
Frontend UI
  ├── Chat Page
  ├── Measurement Page
  └── Debug JSON / Trace Panel
        ↓
FastAPI Backend
        ↓
Agent Orchestrator
  ├── V2.1: V1 workflow, no LangGraph
  └── V2.2+: LangGraph / Graph Workflow
        ↓
Specialist Agents
  ├── Supervisor Agent
  ├── RAG Agent
  ├── Disease Agent
  ├── Measurement Agent
  ├── Safety Agent
  ├── Verifier Agent
  └── Response Agent
        ↓
MCP Tool Layer
  ├── RAG-SERVER MCP Tools
  │   ├── query_knowledge_hub
  │   ├── list_collections
  │   └── get_document_summary
  ├── App MCP Wrappers
  │   ├── livestock_rag_search
  │   ├── get_source_detail
  │   ├── disease_risk_evaluator
  │   └── body_measurement_analyzer
        ↓
Service Layer
  ├── RagServerAdapter
  ├── MeasurementService
  ├── SafetyService
  ├── VerifierService
  ├── EvaluationService
  ├── TraceService
  └── SessionContextService
        ↓
Data Layer
  ├── SQLite / PostgreSQL
  ├── QA Log
  ├── Tool Call Log
  ├── Agent Trace Log
  ├── RAG Trace Log
  ├── Session Context
  ├── Evaluation Results
  └── Animal / Measurement Records
        ↓
External System
  └── Existing RAG-SERVER
```

## 3.2 V2 关键架构变化

相比 V1，V2 新增：

| 新增能力 | 作用 |
|---|---|
| RAG-SERVER 产品级接入 | 从 smoke test 升级为可验收、可降级、可评测 |
| RAG trace | 定位真实检索问题 |
| Multi-agent Workflow | 将职责拆成可测试 Agent 节点 |
| Agent trace | 展示 Agent 执行路径 |
| Session Context | 支持多轮追问续接 |
| Real RAG Eval | 评估真实知识库质量 |
| Frontend Demo | 从 Swagger 演示升级为产品化演示 |
| V2 Harness | 约束 Code Agent / subagent 开发边界 |

---

# 4. LangGraph 引入策略

## 4.1 V2.1 不引入 LangGraph

V2.1 阶段不引入 LangGraph，不改写 V1 既有 workflow，只强化：

- RAG-SERVER 产品级接入
- RAG trace
- real eval
- RAG mode 行为
- MCP schema 固化
- RAG-SERVER timeout / fallback

V2.1 禁止事项：

```text
禁止引入 LangGraph。
禁止重写 V1 Agent Workflow。
禁止修改 V1 三条业务闭环主流程。
禁止实现 LoRA。
禁止启用 Model Router。
禁止实现长期 Memory。
```

## 4.2 V2.2 再引入 LangGraph

V2.2 阶段再正式引入 LangGraph 或明确的图式状态机接口，并要求：

```text
1. V1 三条业务闭环在 LangGraph workflow 下全部通过回归测试。
2. Safety Agent 是最终输出前必经节点。
3. AgentState / MultiAgentState 只保留一套稳定定义。
4. Trace schema 统一由 TraceService 维护。
```

## 4.3 如果不引入 LangGraph

若 V2.2 最终不引入 LangGraph，则必须实现兼容 LangGraph 思路的图式状态机接口，并保持：

- 节点输入输出稳定
- MultiAgentState 稳定
- agent_trace schema 稳定
- 条件分支可测试
- 后续迁移 LangGraph 成本可控

---

# 5. RAG-SERVER 产品级接入设计

## 5.1 V2.1 目标

V1 已完成 RAG-SERVER Adapter、MCP stdio client 和 smoke test。V2.1 需要从“可连通”升级为“可验收、可观测、可降级”。

V2.1 目标：

1. 固化真实 RAG-SERVER MCP tools schema。
2. 明确 fake / smoke / real 三种模式。
3. 增加 RAG status API。
4. 增加 RAG trace。
5. 增加 real RAG eval。
6. 明确 RAG-SERVER timeout、error_code 和 fallback。
7. 保证未配置 RAG_SERVER_PATH 时默认检查不失败。
8. 明确 V2.1 不重新实现 ingestion，只验收既有 ingestion proxy / dry-run 流程。

## 5.2 RAG-SERVER Client 分层

保留并强化现有抽象：

```text
RagServerClient
  ├── FakeRagServerClient
  ├── McpStdioRagServerClient
  └── FutureHttpRagServerClient, optional
```

| Client | 作用 |
|---|---|
| FakeRagServerClient | 默认测试、离线开发、确定性 golden set |
| McpStdioRagServerClient | 真实 RAG-SERVER MCP stdio 接入 |
| FutureHttpRagServerClient | 如果 RAG-SERVER 后续提供 HTTP API，可扩展 |

## 5.3 RAG mode 行为定义

| 模式 | 用途 | 是否允许业务问答 | 是否写 trace | 是否允许 real eval | 默认 CI 是否运行 |
|---|---|---:|---:|---:|---:|
| fake | 默认测试、本地无 RAG-SERVER | 是，使用 fake client | 是 | 否 | 是 |
| smoke | 真实 RAG-SERVER 连通性测试 | 否 | 是 | 否 | optional |
| real | 真实 RAG-SERVER 实际问答 | 是 | 是 | 是 | optional / manual |

规则：

```text
smoke 模式只用于连通性检查，不用于正式业务回答。

默认本地测试和 CI 不依赖真实 RAG-SERVER。

real eval 必须是 optional/manual，不能阻塞普通 CI。
```

`real` 模式未配置 `RAG_SERVER_PATH` 时，必须区分 dev / demo / real eval 三种场景：

| 场景 | 处理规则 |
|---|---|
| dev 本地开发 | 不直接报错，可自动降级到 fake，并在响应 debug / trace 中标记 `rag_mode_effective=fake`、`fallback_reason=RAG_SERVER_PATH_NOT_CONFIGURED` |
| demo 演示 | 不允许静默降级；启动或请求时返回明确错误，提示需要配置 `RAG_SERVER_PATH`，避免演示时误以为使用真实知识库 |
| real eval | 不允许降级到 fake；直接跳过或失败并标记 `RAG_SERVER_PATH_NOT_CONFIGURED`，报告中必须说明 real eval 未执行或失败原因 |

推荐配置：

```yaml
rag:
  mode: fake  # fake / smoke / real
  strict_real_mode: false  # dev=false, demo/eval=true
  rag_server_path: ${RAG_SERVER_PATH}
```

实现要求：

```text
dev 场景允许 fallback，但必须显式记录。
demo 和 real eval 场景禁止静默 fallback。
任何 real 模式的 fallback 都必须写入 rag_trace_log 或 eval report。
```

配置示例：

```yaml
rag:
  mode: fake  # fake / smoke / real
  rag_server_path: ${RAG_SERVER_PATH}
  mcp_command: "python -m src.mcp_server.server"
  default_collection: "livestock_knowledge"
  timeout_seconds: 8
```

## 5.4 RAG-SERVER MCP Tools

当前已支持：

```text
query_knowledge_hub
list_collections
get_document_summary
```

V2.1 必须为每个工具补充：

1. input schema
2. output schema
3. timeout
4. error_code
5. fallback
6. mapper rules
7. trace fields

---

# 6. RAG-SERVER MCP Schema

## 6.1 query_knowledge_hub

### 6.1.1 输入 Schema

```json
{
  "query": "犊牛腹泻持续两天，采食下降的常见原因和处理建议",
  "collection": "livestock_knowledge",
  "top_k": 5,
  "filters": {
    "species": "cattle",
    "domain": "disease"
  }
}
```

### 6.1.2 标准化输出 Schema

业务层只能使用标准化 RetrievedContext，不允许 Agent、Verifier 或前端直接依赖 RAG-SERVER 原始字段。

```json
{
  "results": [
    {
      "rank": 1,
      "doc_id": "doc_001",
      "chunk_id": "chunk_012",
      "collection": "livestock_knowledge",
      "title": "犊牛腹泻防治技术手册",
      "content": "...",
      "source_uri": "rag://livestock_knowledge/doc_001/chunk_012",
      "score": 0.82,
      "score_type": "rag_server_score",
      "raw_score": 0.82,
      "mapped_score": 0.82,
      "metadata": {
        "page": 12,
        "section_title": "常见病因",
        "domain": "disease",
        "species": "cattle"
      }
    }
  ],
  "status": "success",
  "error_code": null,
  "raw_response_id": "rag_trace_xxx"
}
```

### 6.1.3 字段说明

| 字段 | 说明 |
|---|---|
| rank | 检索排序位置，便于评测和前端展示 |
| doc_id | RAG-SERVER 文档 ID |
| chunk_id | RAG-SERVER chunk ID |
| collection | 来源 collection |
| title | 文档标题 |
| content | 检索到的文本内容 |
| source_uri | 标准化来源 URI，便于前端点击和 Debug |
| score | 应用层默认展示分数 |
| score_type | 说明 score 的来源和含义 |
| raw_score | RAG-SERVER 原始分数 |
| mapped_score | 应用层归一或映射后的分数 |
| metadata.page | 页码，可为空 |
| metadata.section_title | 章节标题，可为空 |
| status | success / empty / low_confidence / error |
| error_code | 工具失败或低置信度原因 |
| raw_response_id | 关联 rag_trace_log |

### 6.1.4 错误码

```text
RAG_SERVER_UNAVAILABLE
RAG_SERVER_TIMEOUT
RAG_COLLECTION_NOT_FOUND
RAG_EMPTY_RESULT
RAG_LOW_CONFIDENCE
RAG_BAD_RESPONSE_SCHEMA
RAG_MAPPING_FAILED
RAG_INTERNAL_ERROR
```

### 6.1.5 source_uri 稳定来源 ID 规则

`source_uri` 是 V2 中引用、Verifier、Trace、Eval 的稳定来源 ID，不能只作为前端展示字段。

推荐格式：

```text
rag://{collection}/{doc_id}/{chunk_id}
```

示例：

```text
rag://livestock_knowledge/doc_001/chunk_012
```

使用规则：

```text
回答引用必须优先绑定 source_uri，而不是只绑定 title 或 chunk_id。

Verifier Agent 检查 citation 时必须使用 source_uri 作为稳定 source_id。

rag_trace_log 和 eval result 中必须保留 source_uri，便于失败样例复盘。

如果 RAG-SERVER 缺少 doc_id 或 chunk_id，mapper 必须生成稳定 fallback source_uri，并记录 RAG_MAPPING_PARTIAL_SOURCE_URI。

前端引用点击、Debug Panel、Eval 命中分析都统一使用 source_uri。
```

### 6.1.6 关键规则

```text
RAG-SERVER 原始响应必须写入 trace 或保留 raw_response_id 关联。

业务层只使用标准化 RetrievedContext。

Agent、Verifier、前端不得直接依赖 RAG-SERVER 原始字段。

source_uri 是引用、Verifier、Trace、Eval 的稳定来源 ID。

status == empty 或 low_confidence 时，不允许生成确定性专业结论。

error_code 不为空时，回答必须走 fallback 或明确说明工具失败。
```

## 6.2 list_collections

用途：列出 RAG-SERVER 已有 collection。

标准化输出：

```json
{
  "collections": [
    {
      "name": "livestock_knowledge",
      "description": "畜牧业知识库",
      "document_count": 128,
      "updated_at": "2026-05-12T12:00:00"
    }
  ],
  "status": "success",
  "error_code": null,
  "raw_response_id": "rag_trace_xxx"
}
```

V2 用途：

- 前端展示 RAG-SERVER collection 状态
- Agent 判断某类问题是否有可用知识库
- Evaluation 运行前检查 collection 是否可用

## 6.3 get_document_summary

用途：获取文档摘要。

V2 必须显式传入 collection，避免不同 collection 中 doc_id 冲突。

推荐 Tool 输入：

```json
{
  "collection": "livestock_knowledge",
  "doc_id": "doc_001"
}
```

标准化输出：

```json
{
  "doc_id": "doc_001",
  "collection": "livestock_knowledge",
  "title": "犊牛腹泻防治技术手册",
  "summary": "...",
  "source_uri_prefix": "rag://livestock_knowledge/doc_001",
  "metadata": {
    "domain": "disease",
    "species": "cattle",
    "page_count": 36
  },
  "status": "success",
  "error_code": null,
  "raw_response_id": "rag_trace_xxx"
}
```

关键规则：

```text
get_document_summary 不允许只用 doc_id 查询，必须包含 collection。
如果调用方未传 collection，应使用 default_collection 并在 trace 中记录 collection_resolved_from_default=true。
```

---

# 7. V2 Multi-agent Workflow

## 7.1 为什么加入 Multi-agent

V1 已经完成三条 workflow，但仍然是单 Agent Controller。V2 加入 Multi-agent 的目的不是为了堆概念，而是为了把不同职责拆开，让系统更可解释、更可测试、更容易扩展。

V2 使用：

> Supervisor + Specialist Agents 的轻量 Multi-agent Workflow

不做多个 Agent 自由聊天。

## 7.2 Agent 角色划分

| Agent | 输入 | 输出 | 职责 |
|---|---|---|---|
| Supervisor Agent | user_query、session_context | intent、next_agent、plan | 总调度、任务分发 |
| RAG Agent | query、collection、filters | retrieved_contexts、evidence_status | 调用 RAG-SERVER，整理引用 |
| Disease Agent | disease slots、retrieved_contexts | disease_assessment、draft_answer | 问诊、风险判断、追问 |
| Measurement Agent | current、history、animal_context | measurement_report | 体尺分析、报告草稿 |
| Safety Agent | draft_answer、risk_context | safety_result、safe_answer | 安全审查与改写 |
| Verifier Agent | answer、contexts、tool_results | verification_result | 检查依据、引用、幻觉 |
| Response Agent | safe_answer、sources | final_answer | 生成最终用户可读回答 |

## 7.3 MultiAgentState

```python
class MultiAgentState(BaseModel):
    session_id: str
    user_query: str
    normalized_query: str | None = None

    intent: str | None = None
    route_reason: str | None = None
    active_agent: str | None = None

    session_context: dict = Field(default_factory=dict)
    extracted_slots: dict = Field(default_factory=dict)

    rag_query: str | None = None
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    evidence_status: str | None = None

    disease_assessment: dict | None = None
    measurement_report: dict | None = None

    draft_answer: str | None = None
    verification_result: dict | None = None
    safety_result: dict | None = None
    final_answer: str | None = None

    tool_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[ToolError] = Field(default_factory=list)
    agent_trace: list[dict] = Field(default_factory=list)
```

## 7.4 General QA Workflow

```text
User Query
  ↓
Supervisor Agent
  ↓
RAG Agent
  ↓
Verifier Agent
  ↓
Safety Agent
  ↓
Response Agent
```

规则：

- RAG Agent 检索不到证据时，Response Agent 必须输出无答案策略。
- Verifier Agent 发现无依据结论时，要求重写或拒答。
- Safety Agent 最终兜底。

## 7.5 Disease Consultation Workflow

```text
User Query
  ↓
Supervisor Agent
  ↓
Disease Agent: slot extraction
  ↓
Missing Info Check
  ├── need follow-up → Response Agent
  └── enough info → Disease Risk Evaluator
  ↓
RAG Agent
  ↓
Disease Agent: draft answer
  ↓
Verifier Agent
  ↓
Safety Agent
  ↓
Final Safety Guard
  ↓
Response Agent
```

规则：

- 缺少体温、持续时间、是否群体发病等信息时优先追问。
- 高风险或 emergency 时必须提示联系兽医。
- V2 仍不输出具体药物剂量。
- Safety Agent 是最终输出前必经节点。

## 7.6 Measurement Report Workflow

```text
Measurement Input
  ↓
Supervisor Agent
  ↓
Measurement Agent
  ↓
MeasurementService: load history
  ↓
body_measurement_analyzer
  ↓
RAG Agent: measurement definitions, optional
  ↓
Verifier Agent
  ↓
Safety Agent
  ↓
Response Agent
```

规则：

- history 仍由 MeasurementService 查询，不通过 RAG-SERVER。
- 使用 demo history 必须标注。
- 异常结论必须有 evidence。
- 无历史数据不判断增长趋势。

---

# 8. Session Context 设计

## 8.1 V2 目标

V2 增强多轮追问能力，但不做复杂长期记忆。

V2 实现三类轻量上下文：

| 类型 | 是否持久化 | 用途 |
|---|---|---|
| Session Context | 是，可短期持久化 | 多轮对话中理解“这头牛”“刚才的问题” |
| Animal Context | 是，来自数据库 | 体尺和健康记录分析 |
| RAG Context | 否，单轮 trace 可记录 | 当前回答依据 |

## 8.2 Session Context Schema

```json
{
  "session_id": "s_001",
  "last_intent": "disease_consultation",
  "last_species": "cattle",
  "last_symptoms": ["diarrhea", "low_appetite"],
  "last_animal_id": "yak_032",
  "pending_slots": ["temperature_c", "group_outbreak"],
  "slot_sources": {
    "duration_days": "user_confirmed",
    "temperature_c": "missing",
    "group_outbreak": "missing",
    "symptoms": "user_confirmed",
    "risk_level": "ai_inferred"
  },
  "risk_context_status": "incomplete",
  "updated_at": "2026-05-12T12:00:00",
  "expires_at": "2026-05-12T14:00:00"
}
```

## 8.3 slot_sources 可选值

```text
user_confirmed
ai_inferred
missing
stale
tool_result
```

## 8.4 TTL 规则

| 上下文类型 | TTL |
|---|---:|
| 疾病问诊 pending slots | 2 小时 |
| 普通知识问答上下文 | 24 小时 |
| 体尺报告上下文 | 24 小时 |
| 高风险风险等级 | 不自动复用 |

## 8.5 安全边界

必须遵守：

```text
Session Context 中的槽位必须区分 user_confirmed、ai_inferred、missing、stale 和 tool_result。

高风险疾病问诊中，只能使用 user_confirmed 和 tool_result 信息作为风险判断依据。

超过 TTL 的疾病上下文不得自动复用。

用户明确否定、换动物个体、换物种或开启新问题后，必须清除 pending disease slots。

AI 推断不得写入正式诊断字段。

Session Context 只能辅助理解用户指代，不能作为医学事实来源。

高风险疾病建议不能仅基于历史上下文生成，必须重新确认当前状态。
```

## 8.6 验收样例

```text
用户：牛拉稀了怎么办？
系统：请补充持续时间、体温、是否群体发病。

用户：已经两天了，体温 40 度，不是群体发病。
系统：能够继续上一轮问诊，并基于 user_confirmed 信息进行风险评估。
```

---

# 9. Verifier Agent 设计

## 9.1 能力边界

Verifier Agent 不是事实真值裁判。

它不判断畜牧知识本身是否绝对正确，也不能自行补充新知识。它只能检查回答中的关键结论是否被以下证据支持：

- retrieved_contexts
- tool_results
- measurement evidence
- disease risk evaluator 输出
- session 中 user_confirmed 的上下文

若无法支持，应标记 unsupported_claim，而不是自行补充新知识。

## 9.2 Verifier Agent 输出 Schema

```json
{
  "passed": false,
  "unsupported_claims": [
    {
      "claim": "该牛可能患有某某疾病",
      "reason": "retrieved_contexts 中没有支持该结论的依据",
      "severity": "high"
    }
  ],
  "citation_issues": [
    {
      "source_id": "chunk_012",
      "issue": "citation_not_used_in_answer"
    }
  ],
  "tool_failure_disclosure_missing": false,
  "measurement_evidence_missing": false,
  "need_rewrite": true,
  "rewrite_instruction": "删除无依据疾病名称，仅保留可能原因和建议补充检查。"
}
```

## 9.3 检查项

Verifier Agent 至少检查：

1. 回答是否有引用。
2. 关键专业结论是否被 retrieved_contexts 支持。
3. 工具失败时是否如实说明。
4. 体尺异常是否有数值 evidence。
5. 是否存在 unsupported claims。
6. 是否引用了不存在的 source。
7. 是否在 RAG 低置信度时仍给出确定性结论。

---

# 10. Safety Agent 设计

## 10.1 V1 已有能力

V1 已完成：

- 不输出药物剂量
- 不输出确定性诊断
- 不开处方
- 不伪造工具结果
- Final Safety Guard

## 10.2 V2 增强目标

V2 重点不是放开安全边界，而是增强安全解释和验证能力。

新增能力：

1. Safety Agent 独立化
2. Verifier Agent 独立化
3. 引用支持检查
4. 工具失败声明检查
5. 高风险类型分类
6. Safety trace 记录

## 10.3 Safety Agent 输入输出

输入：

```json
{
  "draft_answer": "...",
  "intent": "disease_consultation",
  "risk_level": "high",
  "tool_errors": [],
  "retrieved_contexts": []
}
```

输出：

```json
{
  "passed": true,
  "violations": [],
  "rewritten_answer": null,
  "required_disclaimer": true,
  "safety_level": "high"
}
```

## 10.4 硬性规则

```text
禁止输出具体药物剂量。
禁止确定性诊断。
禁止直接开处方。
禁止伪造工具结果。
群体发病必须提示隔离和记录。
高风险问题必须提示联系兽医。
Safety Agent / Final Safety Guard 是最终输出前必经节点。
```

---

# 11. V2 Frontend 设计

## 11.1 前端第一版范围

V2 前端第一版以演示闭环为目标，不追求完整管理后台。

P0：

1. Chat Page
2. Measurement Page
3. 可折叠 Debug JSON Panel

P1：

1. RAG-SERVER 状态显示
2. Trace Debug Panel 美化

P2：

1. 完整文档管理后台
2. Collection 管理页面
3. 复杂可视化

## 11.2 Chat Page

功能：

- 问答输入框
- 支持普通问答、疾病问诊、追问回答
- 展示 intent、risk_level
- 展示引用来源
- 展示工具调用摘要
- 展示安全提示
- 可折叠 Debug JSON

## 11.3 Measurement Page

功能：

- 输入 animal_id、体尺数据、confidence
- 展示当前值、历史值、异常项、evidence
- 展示是否使用 demo history
- 展示结构化报告
- 可折叠 Debug JSON

## 11.4 Debug JSON Panel

初版不单独做复杂 Trace 页面，可先在 Chat Page / Measurement Page 加可折叠 JSON Panel，展示：

- request_id
- rag_mode
- default_collection
- mcp_available
- last_rag_error
- tools_used
- agent_path
- retrieved_sources
- safety_result
- verifier_result

---

# 12. V2 Eval 设计

## 12.1 V1 评测限制

V1 fake golden set 60/60 passed，但偏确定性 workflow，无法证明真实 RAG-SERVER 的检索质量。

## 12.2 V2 评测集拆分

```text
data/eval/
├── golden_fake_60.jsonl
├── golden_real_rag_30.jsonl
├── golden_follow_up_10.jsonl
├── golden_safety_20.jsonl
├── golden_measurement_15.jsonl
└── golden_bilingual_intent_10.jsonl
```

## 12.3 Real RAG Eval 指标

| 指标 | 说明 |
|---|---|
| RAG Availability | 真实 RAG-SERVER 是否可用 |
| Collection Availability | 指定 collection 是否存在 |
| Retrieval Hit Rate | 是否检索到预期文档或相关文档 |
| Citation Coverage | 回答是否带真实引用 |
| Evidence Support Rate | 答案是否被检索结果支持 |
| No-answer Correctness | 无证据时是否拒答 |
| Safety Pass Rate | 是否通过安全规则 |
| Failure Category | 失败原因分类 |

Failure Category：

```text
NO_COLLECTION
NO_RETRIEVAL_RESULT
LOW_RETRIEVAL_SCORE
BAD_MAPPING
UNSUPPORTED_CLAIM
SAFETY_VIOLATION
TOOL_TIMEOUT
RAG_SERVER_UNAVAILABLE
```

## 12.4 Multi-agent Eval 指标

| 指标 | 说明 |
|---|---|
| Supervisor Routing Accuracy | Supervisor 是否路由到正确 Agent |
| Agent Path Validity | Agent 执行路径是否符合预期 |
| Follow-up Trigger Accuracy | 是否正确触发追问 |
| Missing Slot Recall | 追问是否覆盖关键槽位 |
| Final Safety Pass Rate | 最终输出是否通过安全校验 |
| Trace Completeness | 是否完整记录 Agent trace |

## 12.5 中英文意图识别 Eval

V2 Router 必须支持中英文畜牧问法的基础识别。优先通过 bilingual keyword + LLM fallback 实现，不引入复杂分类模型。

示例规则：

```text
diarrhea / loose stool / not eating / low appetite / fever / calf / yak / cattle
→ disease_consultation

body height / body length / chest girth / body weight / measurement report
→ measurement_analysis

feeding / nutrition / breeding / vaccination / feed intake
→ general_qa
```

新增 10 条英文或中英混合 eval case：

```text
1. My calf has diarrhea and does not want to eat. What should I do?
2. The yak has had loose stool for two days.
3. Please generate a body measurement report for yak_032.
4. What does chest girth mean in yak measurement?
5. The cattle have fever and low appetite.
```

---

# 13. Trace 与数据库设计

## 13.1 agent_trace_log

```sql
CREATE TABLE agent_trace_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    request_id TEXT,
    trace_json TEXT NOT NULL,
    status TEXT,
    latency_ms INTEGER,
    error_code TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## 13.2 rag_trace_log

```sql
CREATE TABLE rag_trace_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    request_id TEXT,
    rag_mode TEXT,
    collection TEXT,
    query TEXT,
    top_k INTEGER,
    result_count INTEGER,
    mapped_result_count INTEGER,
    top_score REAL,
    raw_response_id TEXT,
    status TEXT,
    error_code TEXT,
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## 13.3 session_context

```sql
CREATE TABLE session_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    context_json TEXT NOT NULL,
    expires_at TEXT,
    status TEXT DEFAULT 'active',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## 13.4 eval_run_log

```sql
CREATE TABLE eval_run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    eval_type TEXT,
    rag_mode TEXT,
    total_cases INTEGER,
    passed_cases INTEGER,
    metrics_json TEXT,
    failure_summary_json TEXT,
    report_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

# 14. V2 API 设计

## 14.1 GET /api/rag/status

用途：查看 RAG-SERVER 状态。

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "rag_mode": "real",
    "rag_server_path_configured": true,
    "mcp_available": true,
    "default_collection": "livestock_knowledge",
    "last_rag_error": null
  },
  "request_id": "req_001"
}
```

## 14.2 GET /api/rag/collections

用途：调用 list_collections。

## 14.3 GET /api/rag/collections/{collection}/documents/{doc_id}/summary

用途：调用 get_document_summary。

路径中必须包含 collection，避免跨 collection 的 doc_id 冲突。

兼容策略：

```text
V2 不推荐保留 /api/rag/documents/{doc_id}/summary。
如需兼容旧路径，必须通过 default_collection 解析，并在 trace 中记录 collection_resolved_from_default=true。
```

## 14.4 GET /api/traces/{request_id}

用途：查看本轮 Agent trace、tool trace、rag trace。

## 14.5 POST /api/eval/run

用途：运行 fake 或 real RAG eval。

请求：

```json
{
  "eval_type": "real_rag",
  "rag_mode": "real",
  "case_file": "golden_real_rag_30.jsonl"
}
```

---

# 15. Model Router 策略

## 15.1 V2 不正式启用多模型路由

V2 不正式启用多模型路由，只保留 ModelRouter 抽象和 model_route_log。实际任务默认走主模型或规则逻辑。V3 再正式启用本地小模型、LoRA 或云端 / 本地分流。

## 15.2 V2 可记录的 route log

```json
{
  "task_type": "slot_extraction",
  "selected_model": "rule_based",
  "route_reason": "v2_default_rule_based",
  "fallback_model": "main_llm",
  "latency_ms": 20
}
```

---

# 16. V2 Harness

## 16.1 新增测试文件

```text
tests/test_rag_server_adapter.py
tests/test_rag_trace.py
tests/test_agent_graph.py
tests/test_session_context.py
tests/test_real_rag_eval.py
tests/test_trace_api.py
tests/test_frontend_contract.py  # optional
```

## 16.2 新增检查脚本

```text
scripts/check_v2.sh
```

建议执行：

```bash
pytest tests/
python scripts/run_eval.py --mode fake
python scripts/run_eval.py --mode real --optional
python scripts/check_trace_schema.py
python scripts/check_mcp_schema.py
```

## 16.3 HARNESS.md 新增规则

```text
Code Agent 修改 RAG-SERVER adapter 后，必须运行 tests/test_rag_server_adapter.py 和 fake eval。

Code Agent 修改 RAG-SERVER MCP schema 后，必须同步 MCP_SPEC.md，并运行 tests/test_mcp_schema.py 或 scripts/check_mcp_schema.py。

Code Agent 修改 Multi-agent workflow 后，必须运行 tests/test_agent_graph.py、tests/test_safety.py 和 fake eval。

Code Agent 修改 Session Context 后，必须运行 tests/test_session_context.py 和 multi-turn follow-up eval。

Code Agent 修改 Trace schema 后，必须运行 tests/test_trace_api.py 和 scripts/check_trace_schema.py。

Code Agent 不得在 V2.1 引入 LangGraph。

Code Agent 不得绕过 Final Safety Guard。

Code Agent 不得实现 V3 功能，包括 LoRA、长期 Farm Memory、大规模权限系统。
```

---

# 17. Ingestion 边界

## 18.1 V2.1 不重新实现 ingestion

V1 已经完成 CLI ingestion gateway，只代理 `RAG-SERVER/scripts/ingest.py`。V2.1 不重新实现 ingestion、切片、embedding、向量库、BM25 或文档管理后台。

V2.1 只做以下验收：

```text
1. ingestion proxy 能正确解析 RAG_SERVER_PATH。
2. dry-run 能调用既有 RAG-SERVER/scripts/ingest.py。
3. ingestion task 能记录状态、错误信息和耗时。
4. ingestion 失败时返回明确错误，不影响默认 fake 测试。
5. 前端或 API 只展示 ingestion proxy 状态，不承诺完整文档管理能力。
```

## 17.2 Ingestion 与 RAG-SERVER 的职责边界

| 能力 | 归属 |
|---|---|
| 文档切片 | RAG-SERVER |
| embedding | RAG-SERVER |
| 向量库 / BM25 | RAG-SERVER |
| ingest.py 执行 | RAG-SERVER |
| ingestion proxy | 当前应用 |
| ingestion task 状态展示 | 当前应用 |
| RAG 查询和 Agent 编排 | 当前应用 |

---

# 18. V2 分阶段开发任务

## 18.1 V2.1：真实 RAG-SERVER 接入与验收

目标：先把真实 RAG 接稳，不引入 LangGraph，不改写 V1 workflow。

必须完成：

- `/api/rag/status`
- `/api/rag/collections`
- `/api/rag/collections/{collection}/documents/{doc_id}/summary`
- RAG-SERVER MCP schema 固化
- RAG mapper 标准化输出
- rag_trace_log
- timeout / fallback
- real smoke test
- 既有 ingestion proxy / dry-run 验收
- 20-30 条 real RAG eval case
- failure category
- `tests/test_rag_server_adapter.py`
- `tests/test_rag_trace.py`

不允许做：

- 不引入 LangGraph
- 不改写 V1 Agent Workflow
- 不做前端复杂页面
- 不启用 Model Router
- 不实现 LoRA
- 不实现长期 Memory
- 不重新实现 ingestion、切片、embedding、向量库或 BM25

验收标准：

```text
1. 未配置 RAG_SERVER_PATH 时，默认测试不失败。
2. dev 场景可降级 fake，但必须显式记录 fallback_reason。
3. demo 和 real eval 场景不得静默降级。
4. 配置 RAG_SERVER_PATH 后，real smoke test 可运行。
5. fake eval 继续通过。
6. real eval 可以 optional/manual 运行。
7. RAG-SERVER 失败时不伪造引用。
8. 所有真实 RAG 调用都写入 rag_trace_log。
9. get_document_summary API 使用 collection 路径。
10. source_uri 在引用、Verifier、Trace、Eval 中保持一致。
11. 只验收既有 ingestion proxy / dry-run，不重新实现 ingestion。
```

## 18.2 V2.2：Multi-agent Workflow

目标：将 V1 workflow 迁移为 Supervisor + Specialist Agents。

必须完成：

- MultiAgentState
- Supervisor Agent
- RAG Agent
- Disease Agent
- Measurement Agent
- Safety Agent
- Verifier Agent
- Response Agent
- agent_trace_log
- `tests/test_agent_graph.py`
- multi-agent fake eval

关键规则：

```text
Safety Agent 必须是最终输出前必经节点。
三条业务闭环必须全部回归通过。
不得输出具体药物剂量。
不得输出确定性诊断。
RAG 低置信度时必须触发无答案或保守回答。
```

## 18.3 V2.3：前端可演示闭环

目标：面试时不用 Swagger 也能演示。

必须完成：

- Chat 页面
- Measurement 页面
- 引用展示
- risk_level 展示
- 工具调用摘要
- 可折叠 Debug JSON Panel

可后置：

- 完整 Document 管理页
- Collection 管理页
- Trace 美化
- 复杂可视化

## 18.4 V2.4：Session Context 多轮追问

目标：疾病问诊可以续接上下文，但不污染安全判断。

必须完成：

- session_context 表
- SessionContextService
- pending_slots
- slot_sources
- TTL
- user_confirmed / ai_inferred / missing / stale 标记
- 用户否定或换动物后清理上下文
- 多轮 follow-up eval
- `tests/test_session_context.py`

验收样例：

```text
用户：牛拉稀了怎么办？
系统：请补充持续时间、体温、是否群体发病。

用户：已经两天了，体温 40 度，不是群体发病。
系统：能够继续上一轮问诊，并基于 user_confirmed 信息进行风险评估。
```

## 18.5 V2.5：真实评测和报告完善

目标：能说明真实 RAG-SERVER 的质量瓶颈。

必须完成：

- real_rag eval
- multi_agent eval
- failure category
- eval_run_log
- failure analysis report
- V2 README
- Demo script
- Interview notes

---

# 19. Codex / Subagent 开发约束

## 19.1 V2.1 推荐 Prompt 约束

```text
本轮开发 V2.1，只允许做 RAG-SERVER 产品级接入，不允许引入 LangGraph，不允许改写 V1 workflow，不允许修改 Safety 规则，不允许实现 LoRA，不允许做复杂前端。

必须保证：

1. pytest tests/ 全部通过。
2. fake eval 仍然通过。
3. 未配置 RAG_SERVER_PATH 时，本地默认检查不失败。
4. 配置 RAG_SERVER_PATH 时，real smoke test 可运行。
5. RAG-SERVER 失败时，不伪造引用。
6. 所有真实 RAG 调用都写入 rag_trace_log。
7. 所有 API 响应保持统一格式。
8. 修改 RAG-SERVER schema 后必须同步 MCP_SPEC.md。
9. real 模式未配置 RAG_SERVER_PATH 时，必须按 dev/demo/real eval 场景处理。
10. get_document_summary 必须显式包含 collection。
11. source_uri 必须作为引用、Verifier、Trace、Eval 的稳定来源 ID。
12. 不重新实现 ingestion，只验收既有 ingestion proxy / dry-run。
```

## 19.2 V2.2 推荐 Prompt 约束

```text
本轮开发 V2.2，只允许实现 Multi-agent Workflow。

允许修改：

- backend/app/agent/
- backend/app/services/trace_service.py
- backend/app/models/agent_trace_log.py
- tests/test_agent_graph.py
- docs 中与 Multi-agent 相关部分

不允许修改：

- RAG-SERVER adapter 的既有 schema
- Safety 禁止规则
- API 统一响应格式
- V1 数据库表结构，除非迁移文件明确记录
- V3 功能

必须保证：

1. V1 三条业务闭环继续通过。
2. Safety Agent 是最终输出前必经节点。
3. Agent trace 能记录节点路径、耗时和状态。
4. fake eval 继续通过。
5. pytest tests/ 全部通过。
```

## 19.3 V2.3 推荐 Prompt 约束

```text
本轮开发 V2.3，只做前端可演示闭环。

优先实现：

1. Chat Page
2. Measurement Page
3. 引用展示
4. risk_level 展示
5. 工具调用摘要
6. 可折叠 Debug JSON Panel

不做：

1. 完整文档管理后台
2. 复杂权限系统
3. 复杂可视化
4. V3 功能

前端必须遵守 API_SPEC.md，不得要求后端改变统一响应格式。
```

---

# 20. V2 验收标准

完成 V2 后，应满足：

1. **范围可控**：V2 被拆成清晰子阶段，不一次性大重构。
2. **RAG 接入可靠**：真实 RAG-SERVER 有 schema、trace、timeout、fallback 和 real eval。
3. **Workflow 可迁移**：V2.1 不动 V1 workflow，V2.2 再引入 Multi-agent。
4. **安全不放松**：Safety Agent / Final Safety Guard 仍是最终输出硬约束。
5. **上下文不污染**：Session Context 有 TTL、slot_sources 和 stale 机制。
6. **Verifier 可测试**：Verifier Agent 有明确 JSON 输出和证据支持边界。
7. **评测更真实**：fake eval 做回归，real eval 做真实质量验证。
8. **前端可演示**：Chat、Measurement 和 Debug Panel 足够面试展示。
9. **Codex 可控**：V2 Harness 能限制 subagent 改动范围。
10. **V1 不被破坏**：每个 V2 子阶段都必须保持 V1 已有测试和 fake eval 通过。
11. **real 模式语义清晰**：dev 可显式降级，demo / real eval 不允许静默降级。
12. **source_uri 稳定一致**：引用、Verifier、Trace、Eval 均使用 source_uri 作为来源 ID。
13. **ingestion 边界清楚**：V2.1 只验收既有 ingestion proxy / dry-run，不重新实现 RAG ingestion。

---

# 21. V2 简历描述更新

完成 V2 后，简历可以升级为：

> 基于既有 RAG-SERVER 构建畜牧业 Multi-agent MCP 智能助手，将外部 RAG-SERVER 通过 MCP stdio 接入应用层 Agent 系统，封装 query_knowledge_hub、list_collections、get_document_summary 等知识工具，并基于 LangGraph / 图式状态机构建 Supervisor、RAG、Disease、Measurement、Safety、Verifier 等多 Agent 节点，实现疾病问诊、畜牧知识问答和牦牛体尺报告的多步协作流程。设计 Agent trace、tool trace、RAG trace 与真实 RAG golden set 评测，支持 fake/real 双模式验证和失败样例分析；针对疾病、用药等高风险问题保留 Final Safety Guard，避免确定性诊断和具体药物剂量输出。

---

# 22. 最终建议

当前 V2 文档不需要推倒重写。最推荐的第一步不是 Multi-agent，而是：

```text
V2.1：RAG-SERVER 产品级接入与真实评测
```

原因：

1. V1 最大短板是真实 RAG 质量没有被证明。
2. Multi-agent 的价值依赖真实工具结果。
3. 先接稳 RAG-SERVER，再把调用流程升级为 LangGraph / Multi-agent，风险更低。
4. 面试时，“真实 RAG-SERVER 接入 + trace + failure analysis”比“概念上的多 Agent”更有说服力。

一句话总结：

> V2 的核心不是继续堆功能，而是把 V1 的应用闭环升级为“真实 RAG-SERVER 接入稳定、Multi-agent 可解释、Trace 可观测、Real Eval 可分析、前端可演示”的工程化系统。开发时必须先做 V2.1，确保真实 RAG 接入、source_uri 来源标识、RAG mode 语义、ingestion proxy 验收和回归测试稳定，再进入 Multi-agent 重构。
