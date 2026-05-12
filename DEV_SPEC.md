# DEV_SPEC：畜牧业 Multi-agent MCP 智能助手 V2 开发规范

> 版本：V2 阶段开发规范初稿
> 设计来源：`畜牧业_Agentic_RAG_智能助手_V2设计文档_修订版v2.md`、`AGENTS.md`
> 当前基线：V1 已完成应用层闭环，`RAG-SERVER` 是已存在的独立 RAG 系统
> 默认约束：Python、pytest、本地优先、默认测试零外部服务依赖、每个小阶段完成后提交简体中文 commit

本文档用于指导 V2 阶段开发。V2 不是推倒 V1，也不是重写 RAG。V2 的核心是把 V1 的应用闭环升级为：

```text
真实 RAG-SERVER 接入稳定
Multi-agent 工作流可解释
Trace 可观测
Real Eval 可分析
前端可演示
Session Context 可续接
Code Agent 开发过程可约束
```

硬性前提：

- 不重新实现 `RAG-SERVER` 已有的 parser、splitter、embedding、向量库、BM25、rerank、RAG citation、Dashboard。
- V2.1 先做真实 RAG-SERVER 产品级接入和真实评测。
- V2.2 再做 Multi-agent Workflow。
- 每个 V2 子阶段完成后，必须保持 V1 回归通过。
- 每个小阶段任务完成并通过验收后，必须使用简体中文 commit 消息提交。

---

## 1. 项目概述

### 1.1 设计理念

| 原则 | 说明 |
|---|---|
| 复用既有 RAG | `RAG-SERVER` 是知识检索核心，本项目只做产品级接入、Agent 编排、评测和前端。 |
| 先真实接入，后 Multi-agent | V2.1 先证明真实 RAG 可用、可观测、可降级，再进入 V2.2 Multi-agent。 |
| 可控 Multi-agent | 只做 Supervisor + Specialist Agents 的图式工作流，不做多个 Agent 自由聊天。 |
| Trace 优先 | RAG trace、tool trace、agent trace 是 V2 质量定位的基础能力。 |
| fake 与 real 分离 | fake eval 做回归，real eval 才用于真实 RAG 质量验证。 |
| 安全边界不放松 | V2 仍禁止具体药物剂量、确定性诊断和直接处方。 |
| 小步提交 | 每个小阶段通过测试后，用简体中文 commit 消息提交，避免大批量不可审查改动。 |

### 1.2 项目定位

项目名称：

```text
基于既有 RAG-SERVER 的畜牧业 Multi-agent MCP 智能助手
```

V2 定位：

- V1 已完成 FastAPI、SQLite、RAG-SERVER Adapter、MCP Wrapper、规则安全、体尺分析、三条业务闭环、fake golden set。
- V2 要把系统升级为真实可演示、可追踪、可评测的工程化 Agent 系统。
- `RAG-SERVER` 继续作为外部 sibling 项目存在，通过 MCP stdio / CLI ingestion proxy 接入。

### 1.3 V2 分段目标

```text
V2.1：真实 RAG-SERVER 接入 + RAG trace + real eval
V2.2：Multi-agent Workflow + Agent trace + Safety/Verifier Agent
V2.3：前端 UI + Debug JSON / Trace Panel
V2.4：Session Context 多轮追问增强
V2.5：真实评测报告、失败分析和面试材料完善
```

依赖关系：

| 阶段 | 依赖 | 目的 |
|---|---|---|
| V2.1 | V1 | 将真实 RAG-SERVER 接稳。 |
| V2.2 | V2.1 | 在真实 RAG 稳定后引入 Multi-agent。 |
| V2.3 | V2.1/V2.2 | 提供可演示前端，API 稳定后可部分并行。 |
| V2.4 | V2.2 | Session Context 需要接入 Multi-agent workflow。 |
| V2.5 | 全阶段 | 汇总 real eval、trace、失败分析和展示材料。 |

### 1.4 V2 不做事项

- 不重写 RAG-SERVER ingestion、切片、embedding、向量库、BM25、rerank。
- V2.1 不引入 LangGraph，不改写 V1 workflow。
- V2 不正式启用多模型路由，只保留抽象和 route log。
- 不实现 LoRA、长期 Farm Memory、大规模权限系统。
- 不把 fake eval 作为真实 RAG 质量证明。
- 不在默认 CI / 默认本地检查中强制启动真实 RAG-SERVER。

---

## 2. 核心特点

| 核心特点 | 简要说明 |
|---|---|
| 真实 RAG-SERVER 产品级接入 | 从 smoke test 升级为 schema 固化、timeout、fallback、trace、real eval。 |
| RAG mode 语义 | 明确 fake / smoke / real 三种模式，dev 可显式降级，demo/eval 禁止静默降级。 |
| source_uri 稳定来源 ID | 引用、Verifier、Trace、Eval 均使用 `source_uri` 作为来源标识。 |
| Multi-agent 工作流 | Supervisor、RAG、Disease、Measurement、Safety、Verifier、Response 等 Agent 可测试协作。 |
| Session Context | 支持多轮追问续接，并记录 `slot_sources`、TTL、stale 状态。 |
| Trace 可观测 | 新增 `rag_trace_log`、`agent_trace_log`、trace API 和 Debug Panel。 |
| Real RAG Eval | 区分 fake 回归评测和真实 RAG 质量评测，输出失败类别。 |
| 前端演示闭环 | Chat、Measurement、引用展示、工具摘要、Debug JSON Panel。 |
| V2 Harness | 用测试、文档、脚本和提交规则约束 Code Agent / subagent。 |

---

## 3. 技术选型

### 3.1 V2 默认技术栈

| 模块 | V2 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | 后端应用层和测试。 |
| Web API | FastAPI | 保持 V1 API 风格，新增 RAG / trace / eval API。 |
| 数据校验 | Pydantic | API、RAG schema、MultiAgentState、Trace schema。 |
| 数据库 | SQLite | V2 继续本地优先；新增 trace、session、eval 表。 |
| RAG | 既有 RAG-SERVER | 通过 MCP stdio 接入，不重写底层 RAG。 |
| Agent 编排 | V2.1 保持 V1 workflow；V2.2 引入 LangGraph 或图式状态机接口 | 先稳定真实 RAG，再做 Multi-agent。 |
| 前端 | FastAPI 静态页面 + 原生 JS/CSS | V2.3 默认不引入 Node/Vite/React，优先轻量演示闭环。 |
| 测试 | pytest | 单元、集成、E2E、real eval optional。 |
| 质量检查 | `scripts/check_all.py`、`scripts/check_v2.py` | `check_v2.py` 由 V2.1-A0 创建；默认不跑真实 RAG。 |

### 3.2 本地虚拟环境规范

当前项目必须使用项目根目录下的 `.venv` 作为全程开发和测试环境。后续 code agent 执行安装、测试、脚本、评测时，默认使用当前项目 `.venv` 中的 Python。

Windows PowerShell 初始化命令：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest -m "not rag_server"
```

规则：

- `.venv/` 必须加入 `.gitignore`，不得提交。
- 当前项目使用自己的 `.venv`；`RAG-SERVER` 作为独立 sibling 项目，可以使用自己的环境。
- 不把 RAG-SERVER 的依赖整体复制进当前项目，只声明 adapter、API、Agent、前端、测试所需依赖。
- 调用真实 RAG-SERVER 时，优先使用 `rag_server.python_executable` 指向 RAG-SERVER 可用 Python。
- 创建 `.venv` 不意味着默认测试必须安装或启动真实 RAG-SERVER。

### 3.3 Git 与提交规范

每个小阶段任务完成后必须提交一次 commit，commit 消息使用简体中文，说明完成的阶段、核心改动和验证结果。

提交流程：

```powershell
python -m pytest -m "not rag_server"
python scripts/run_eval.py --mode fake
git status --short
git add <本阶段修改文件>
git commit -m "V2.1-A1：新增 RAG 状态 API 契约并通过本地回归"
```

提交前必须检查 `git status --short`。优先使用 `git add <本阶段修改文件>` 精确暂存本阶段改动；不得在未审查状态下直接使用 `git add .`。

commit 消息格式：

```text
V2.x-任务编号：动词 + 具体改动 + 验证结果
```

示例：

```text
V2.1-A3：固化 query_knowledge_hub 映射并通过 fake 回归
V2.2-B4：新增 Safety Agent 节点并通过安全测试
V2.4-D2：实现会话槽位续接并通过多轮追问评测
```

提交规则：

- 不允许多个阶段混在一个 commit。
- 不允许未通过当前阶段验收测试就提交。
- commit 消息必须是简体中文。
- 如果真实 RAG 测试因未配置 `RAG_SERVER_PATH` 被跳过，commit 消息或提交说明中必须写明。
- 不提交 `.venv/`、`.pytest_cache/`、临时日志、大型运行数据和真实密钥。

### 3.4 RAG-SERVER 依赖原则

- RAG-SERVER 真正 MCP 入口是 `python -m src.mcp_server.server`。
- 不要假设 `mcp-server` console script 能启动真实 MCP server。
- RAG-SERVER stdio 的 stdout 保留给 JSON-RPC，日志必须走 stderr。
- 默认测试不得要求网络、API key、GPU、远程数据库或真实 RAG-SERVER 进程。
- `RAG_SERVER_PATH` > `settings.yaml` 的 `rag_server.repo_path`；相对路径相对当前项目根目录解析。
- V2.1 不重新实现 ingestion，只验收既有 ingestion proxy / dry-run。

### 3.5 RAG 配置命名兼容策略

V2 不新建 `rag.*` 并行配置块，继续使用当前项目已有的 `rag_server.*`。V2.1-A1 只在这个配置块内做向前兼容扩展。

| 配置项 | V1 当前语义 | V2 语义 | 兼容要求 |
|---|---|---|---|
| `rag_server.query_mode` | `fake` / `mcp_stdio` | 逐步扩展为 `fake` / `smoke` / `real` | `mcp_stdio` 必须作为旧别名兼容到 `real` 或保留为 adapter 层真实 MCP 模式。 |
| `rag_server.repo_path` | RAG-SERVER sibling 路径 | 真实 RAG-SERVER 路径 | 环境变量 `RAG_SERVER_PATH` 优先覆盖。 |
| `rag_server.python_executable` | 可选 Python 路径 | 调用 RAG-SERVER 的 Python | 不配置时才使用当前 `.venv` 的 Python。 |
| `rag_server.collection` | 默认 collection | default_collection | 未传 collection 时使用，并在 trace 记录 `collection_resolved_from_default=true`。 |
| `rag_server.timeout_seconds` | MCP 调用超时 | MCP 调用超时 | timeout 必须写入 `rag_trace_log`。 |

V2.1-A1 验收测试必须覆盖：旧配置 `query_mode=mcp_stdio` 不会导致配置加载失败；新配置 `query_mode=fake/smoke/real` 可加载；不存在新的 `rag.*` 并行配置依赖。

---

## 4. 测试方案

### 4.1 TDD 与回归要求

每个 V2 小阶段遵循：

```text
写失败测试 -> 实现最小代码 -> 跑通当前测试 -> 跑 V1 回归 -> 简体中文 commit
```

每个 V2 子阶段完成后必须保证：

```text
1. pytest tests/ 全部通过，真实 RAG 测试可用 marker 排除。
2. fake golden-set eval 继续通过。
3. API contract 不破坏统一响应格式。
4. Safety tests 继续通过。
5. 三条 V1 业务闭环继续可用。
6. 未配置 RAG_SERVER_PATH 时，默认本地检查不失败。
```

### 4.2 测试目录规划

```text
tests/
├── unit/
│   ├── test_rag_schema.py
│   ├── test_rag_mapper.py
│   ├── test_trace_schema.py
│   ├── test_multi_agent_state.py
│   ├── test_supervisor_agent.py
│   ├── test_verifier_agent.py
│   ├── test_safety_agent.py
│   ├── test_session_context.py
│   └── test_eval_metrics.py
├── integration/
│   ├── test_rag_server_adapter.py
│   ├── test_rag_trace.py
│   ├── test_rag_api.py
│   ├── test_agent_graph.py
│   ├── test_trace_api.py
│   ├── test_eval_runner.py
│   └── test_frontend_contract.py
├── e2e/
│   ├── test_v1_regression_flows.py
│   ├── test_multi_agent_flows.py
│   ├── test_session_follow_up_flow.py
│   └── test_frontend_smoke.py
└── fixtures/
    ├── eval/
    ├── rag_server/
    └── frontend/
```

### 4.3 默认测试命令

V2.1-A0 是强制前置任务。A0 之前，当前仓库已有的 fake eval 命令是：

```powershell
python scripts/run_eval.py
```

V2.1-A0 完成后，`scripts/run_eval.py` 必须支持以下 CLI 契约：

| 参数 | 语义 | 实现阶段 |
|---|---|---|
| `--mode fake` | 运行当前 fake golden set，等价于 V1 既有 eval。 | V2.1-A0 |
| `--mode real` | 运行真实 RAG eval。 | V2.1-A11 |
| `--optional` | 真实 RAG 未配置时不让默认检查失败，输出 skipped report。 | V2.1-A11 |
| `--json` | 保持 V1 已有 JSON 输出。 | V2.1-A0 必须兼容 |

默认本地检查：

```powershell
python -m pytest -m "not rag_server"
python scripts/run_eval.py --mode fake
python scripts/check_v2.py --offline
```

真实 RAG-SERVER 可选检查：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
python -m pytest -m rag_server
python scripts/run_eval.py --mode real --optional
```

真实 RAG-SERVER 可选检查只有在 V2.1-A11 完成后才作为正式命令；A11 前只允许运行 `pytest -m rag_server` smoke test。

### 4.4 V2 评测集

```text
data/eval/
├── golden_fake_60.jsonl
├── golden_real_rag_30.jsonl
├── golden_follow_up_10.jsonl
├── golden_safety_20.jsonl
├── golden_measurement_15.jsonl
└── golden_bilingual_intent_10.jsonl
```

### 4.5 V2 关键指标

| 指标 | 说明 |
|---|---|
| RAG Availability | 真实 RAG-SERVER 是否可用。 |
| Collection Availability | 指定 collection 是否存在。 |
| Retrieval Hit Rate | 是否检索到预期文档或相关文档。 |
| Citation Coverage | 回答是否带真实引用。 |
| Evidence Support Rate | 答案是否被检索结果支持。 |
| No-answer Correctness | 无证据时是否拒答。 |
| Safety Pass Rate | 是否通过安全规则。 |
| Supervisor Routing Accuracy | Supervisor 是否路由到正确 Agent。 |
| Agent Path Validity | Agent 执行路径是否符合预期。 |
| Follow-up Trigger Accuracy | 是否正确触发追问。 |
| Trace Completeness | Trace 是否完整记录。 |

失败类别：

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

---

## 5. 系统架构与模块设计

### 5.1 V2 整体架构图

```text
Frontend UI
  ├── Chat Page
  ├── Measurement Page
  └── Debug JSON / Trace Panel
        |
        v
FastAPI Backend
        |
        v
Agent Orchestrator
  ├── V2.1: V1 workflow, no LangGraph
  └── V2.2+: LangGraph / Graph Workflow
        |
        v
Specialist Agents
  ├── Supervisor Agent
  ├── RAG Agent
  ├── Disease Agent
  ├── Measurement Agent
  ├── Safety Agent
  ├── Verifier Agent
  └── Response Agent
        |
        v
MCP Tool Layer
  ├── RAG-SERVER MCP Tools
  │   ├── query_knowledge_hub
  │   ├── list_collections
  │   └── get_document_summary
  └── App MCP Wrappers
      ├── livestock_rag_search
      ├── get_source_detail
      ├── disease_risk_evaluator
      └── body_measurement_analyzer
        |
        v
Service Layer
  ├── RagServerAdapter
  ├── MeasurementService
  ├── SafetyService
  ├── VerifierService
  ├── EvaluationService
  ├── TraceService
  └── SessionContextService
        |
        v
Data Layer
  ├── SQLite
  ├── QA Log / Tool Call Log
  ├── RAG Trace Log / Agent Trace Log
  ├── Session Context
  ├── Eval Run Log
  └── Animal / Measurement Records
        |
        v
External System
  └── Existing RAG-SERVER
```

### 5.2 V2 目录结构

```text
backend/app/
├── api/
│   ├── rag.py
│   ├── traces.py
│   ├── eval.py
│   └── existing V1 api modules
├── agent/
│   ├── graph.py
│   ├── supervisor.py
│   ├── rag_agent.py
│   ├── disease_agent.py
│   ├── measurement_agent.py
│   ├── safety_agent.py
│   ├── verifier_agent.py
│   ├── response_agent.py
│   └── state.py
├── integrations/rag_server/
│   ├── schema.py
│   ├── mapper.py
│   ├── mcp_stdio_client.py
│   └── status.py
├── services/
│   ├── trace_service.py
│   ├── session_context_service.py
│   ├── evaluation_service.py
│   └── existing V1 services
├── db/
│   ├── migrations.py
│   └── repositories.py
├── static/frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── evaluation/
    ├── real_rag_runner.py
    ├── multi_agent_runner.py
    └── failure_analysis.py
```

### 5.3 模块职责表

| 模块 | 职责 | 禁止事项 |
|---|---|---|
| RAG Adapter | 固化 RAG-SERVER MCP schema、mapper、mode、timeout、fallback、trace。 | 不重写 RAG 检索逻辑。 |
| TraceService | 写入和读取 rag/tool/agent trace。 | 不把 trace 逻辑散落在 Agent 节点中。 |
| Multi-agent | Supervisor + Specialists 图式工作流。 | 不做 Agent 自由对话。 |
| SessionContextService | 管理 pending slots、slot_sources、TTL、stale。 | 不让 AI 推断信息覆盖用户确认信息。 |
| Verifier Agent | 检查回答是否被证据支持。 | 不自行补充新事实。 |
| Safety Agent | 安全审查和必要改写。 | 不放开药物剂量和确定性诊断。 |
| Frontend | 演示 Chat、Measurement、Debug JSON。 | 不要求后端改变统一响应格式。 |
| Eval | fake/real/multi-agent/follow-up/safety eval。 | 不把 fake eval 当真实 RAG 质量证明。 |

### 5.4 RAG mode 契约

| 模式 | 用途 | 是否允许业务回答 | 是否写 trace | 是否允许 real eval | 默认检查 |
|---|---|---:|---:|---:|---:|
| fake | 默认测试、本地无 RAG-SERVER | 是 | 是 | 否 | 是 |
| smoke | 真实 RAG-SERVER 连通性测试 | 否 | 是 | 否 | 否 |
| real | 真实 RAG-SERVER 实际问答 | 是 | 是 | 是 | 否 |

real 模式缺少 `RAG_SERVER_PATH` 时：

| 场景 | 处理 |
|---|---|
| dev | 可显式降级 fake，必须记录 `rag_mode_effective=fake` 和 `fallback_reason=RAG_SERVER_PATH_NOT_CONFIGURED`。 |
| demo | 不允许静默降级，返回明确错误。 |
| real eval | 不允许降级，跳过或失败并写入报告。 |

### 5.5 RAG-SERVER MCP 标准化输出

业务层只能使用标准化 `RetrievedContext`，不得直接依赖 RAG-SERVER 原始字段。

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

#### 5.5.1 真实 MCP 响应解析规则

`query_knowledge_hub`、`list_collections`、`get_document_summary` 都来自 RAG-SERVER MCP stdio。当前项目的 mapper 必须先把原始 MCP `CallToolResult` 统一保存到 trace，再按以下优先级解析；Agent、Verifier、前端不得直接读取原始 MCP 字段。

| 工具 | 原始响应形态 | 标准化规则 | mapping warning |
|---|---|---|---|
| `query_knowledge_hub` | `content[]` 中的 JSON `TextContent` | 优先解析 JSON；`hits`/`results` -> `results[]`；`citations` -> citation 字段；原始 payload 写入 `raw_payload_json` 或 `raw_response_ref`。 | 缺 `doc_id` / `chunk_id` 时记录 `RAG_MAPPING_PARTIAL_SOURCE_URI`。 |
| `query_knowledge_hub` | Markdown / plain text `TextContent` | `answer_text` 取原文；只从明确 citation 行解析来源；无法解析 chunk 时生成 fallback `source_uri`；没有 citation 时 `results=[]`，`status=low_confidence` 或 `empty`。 | 记录 `RAG_MAPPING_TEXT_ONLY_RESPONSE`。 |
| `query_knowledge_hub` | `ImageContent` | 不作为文本证据来源；只写入 `metadata.images[]` 和 trace，引用仍必须绑定文本 `source_uri`。 | 无可追溯文本来源时记录 `RAG_MAPPING_IMAGE_ONLY`。 |
| `list_collections` | JSON 列表或 Markdown 列表 | JSON `collections[]` 优先；Markdown 只解析首列 collection 名称，统计信息放 `metadata`。 | Markdown 解析时记录 `RAG_MAPPING_PARTIAL_COLLECTIONS`。 |
| `get_document_summary` | JSON 或 Markdown 文本 | `doc_id` 以请求参数为准；JSON 字段优先；Markdown 只填 `summary`，缺 title/tags 时保持空值。 | Markdown 解析时记录 `RAG_MAPPING_PARTIAL_SUMMARY`。 |

`source_uri` 生成优先级：

1. `collection` 使用请求参数或 `rag_server.collection` 解析结果。
2. `doc_id` 优先取 `item.doc_id`、`item.document_id`、`item.source_id`、`item.metadata.doc_id`、`item.metadata.document_id`、citation `source_id`。
3. `chunk_id` 优先取 `item.chunk_id`、`item.id`、`item.metadata.chunk_id`、citation `chunk_id`。
4. 缺少 `doc_id` 时生成 `unknown-doc-{sha256(title|source|rank)[:12]}`。
5. 缺少 `chunk_id` 时生成 `unknown-chunk-{sha256(content|page|rank)[:12]}`。
6. 最终格式固定为 `rag://{collection}/{doc_id}/{chunk_id}`。

fallback `source_uri` 只能用于追踪和展示，不得伪装成高置信证据。只要出现 fallback source，`mapping_warnings_json` 必须包含 warning，Verifier 和 Eval 必须能读取。

关键规则：

- `source_uri` 格式优先为 `rag://{collection}/{doc_id}/{chunk_id}`。
- 回答引用、Verifier、Trace、Eval 必须优先使用 `source_uri`。
- RAG-SERVER 缺少 `doc_id` 或 `chunk_id` 时，mapper 必须生成稳定 fallback `source_uri`，并记录 `RAG_MAPPING_PARTIAL_SOURCE_URI`。
- `status == empty` 或 `low_confidence` 时，不允许确定性专业结论。
- `error_code` 不为空时，回答必须 fallback 或明确说明工具失败。

### 5.6 MultiAgentState 契约

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

### 5.7 V2.2 与 V1 现有类迁移关系

V2.2 不是推倒 V1 workflow。新增 Agent 类必须优先包裹、委托或迁移当前已有实现，避免生成两套互相竞争的业务逻辑。

| V1 现有模块 / 类 | V2.2 目标 | 处理方式 | 禁止事项 |
|---|---|---|---|
| `backend/app/agent/workflow.py` | `backend/app/agent/graph.py` | 保留 V1 入口作为兼容 facade；内部逐步调用 graph。 | 不得一次性删除 V1 workflow。 |
| `backend/app/agent/router.py` / `IntentRouter` | `SupervisorAgent.route` | Supervisor 复用现有意图规则，并补充 agent trace。 | 不得维护第二套互斥路由规则。 |
| `backend/app/agent/extractor.py` | `DiseaseAgent.run` | Disease Agent 复用槽位抽取和追问策略。 | 不得让疾病追问绕过现有 slot tests。 |
| `backend/app/agent/safety.py` / `SafetyGuard`、`FinalSafetyGuard` | `SafetyAgent.check` | Safety Agent 作为 wrapper，规则文件和禁止项保持不变。 | 不得放开剂量、确定性诊断或处方限制。 |
| `backend/app/agent/verifier.py` / `VerifierLite` | `VerifierAgent.verify` | Verifier Agent 复用现有无引用结论、剂量、体尺证据检查。 | 不得只做空实现来通过流程图。 |
| `backend/app/services/measurement_service.py` | `MeasurementAgent.run` | Measurement Agent 委托现有体尺分析服务，history 仍查本项目 SQLite。 | 不得通过 RAG-SERVER 查询体尺历史。 |
| `backend/app/integrations/rag_server/*` | `RagAgent.run` | Rag Agent 只调用 V2.1 固化后的 adapter schema。 | V2.2 不得修改 RAG adapter schema。 |

V2.2-B1 到 B3 必须先建立 compatibility tests，证明 V1 `run_general_qa`、疾病问诊、体尺分析入口仍可工作，再逐步把内部实现接到 graph。

### 5.8 新增数据库表

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
    source_uris_json TEXT,
    fallback_reason TEXT,
    mapping_warnings_json TEXT,
    raw_payload_json TEXT,
    raw_response_ref TEXT,
    raw_response_id TEXT,
    status TEXT,
    error_code TEXT,
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    context_json TEXT NOT NULL,
    expires_at TEXT,
    status TEXT DEFAULT 'active',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

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

### 5.9 Session Context 契约

`session_context.context_json` 必须保存以下稳定结构，不能只保存任意 dict：

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

`slot_sources` 只允许：

```text
user_confirmed
ai_inferred
missing
stale
tool_result
```

TTL 规则：

| 上下文类型 | TTL | 安全规则 |
|---|---:|---|
| 疾病问诊 pending slots | 2 小时 | 超时后不得自动复用。 |
| 普通知识问答上下文 | 24 小时 | 只用于指代消解，不作为证据来源。 |
| 体尺报告上下文 | 24 小时 | 只复用 animal_id / 最近报告入口，不复用异常结论。 |
| 高风险风险等级 | 不自动复用 | 必须重新确认当前状态。 |

安全边界：

- 高风险疾病问诊中，只能使用 `user_confirmed` 和 `tool_result` 信息作为风险判断依据。
- `ai_inferred` 不得写入正式诊断字段，不得单独触发高风险结论。
- 用户明确否定、换动物个体、换物种或开启新问题后，必须清除 pending disease slots。
- Session Context 只能辅助理解“这头牛”“刚才的问题”等指代，不能作为医学事实来源。

### 5.10 新增 API 契约

`GET /api/rag/status`

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "rag_mode": "real",
    "rag_mode_effective": "real",
    "rag_server_path_configured": true,
    "mcp_available": true,
    "default_collection": "livestock_knowledge",
    "last_rag_error": null
  },
  "request_id": "req_001"
}
```

`GET /api/rag/collections`

- 调用 `list_collections`。
- 失败时返回统一响应，不抛原始 MCP 错误。

`GET /api/rag/collections/{collection}/documents/{doc_id}/summary`

- 必须显式包含 `collection`，避免跨 collection 的 `doc_id` 冲突。
- 若保留旧路径，必须使用 `default_collection` 解析并写 trace。

`GET /api/traces/{request_id}`

返回本轮：

```text
agent_trace
tool_trace
rag_trace
safety_result
verifier_result
```

`POST /api/eval/run`

```json
{
  "eval_type": "real_rag",
  "rag_mode": "real",
  "case_file": "golden_real_rag_30.jsonl"
}
```

---

## 6. 项目排期

每个小任务目标是约 1 小时可验收。每个小任务完成后必须：

```text
1. 激活 .venv。
2. 运行该任务指定测试。
3. 运行必要的 V1 回归。
4. 使用简体中文 commit 消息提交。
```

### 6.1 V2.1：真实 RAG-SERVER 接入与验收

目标：真实 RAG 接稳，不引入 LangGraph，不改写 V1 workflow。

| ID | 小阶段任务 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 | commit 消息示例 |
|---|---|---|---|---|---|---|
| V2.1-A0 | 补齐 V2 开发环境与检查脚本 | `.gitignore`、`pyproject.toml`、`scripts/check_v2.py`、`scripts/run_eval.py`、`tests/integration/test_cli_scripts.py` | `check_v2.main`、`run_eval.main` | `.venv/` 已忽略；`check_v2 --offline` 默认不触发真实 RAG；`run_eval.py --mode fake` 等价于 V1 fake eval | `python scripts/check_v2.py --offline`、`python scripts/run_eval.py --mode fake` | `V2.1-A0：补齐 V2 检查脚本并通过离线检查` |
| V2.1-A1 | 固化 RAG mode 配置 | `config/settings.yaml`、`backend/app/core/config.py`、`tests/unit/test_config.py` | `RagModeSettings` | fake/smoke/real、strict_real_mode 可加载 | `python -m pytest tests/unit/test_config.py` | `V2.1-A1：固化 RAG 模式配置并通过配置测试` |
| V2.1-A2 | 新增 RAG status API | `backend/app/api/rag.py`、`backend/app/services/rag_status_service.py`、`tests/integration/test_rag_api.py` | `get_rag_status` | 未配置 RAG_SERVER_PATH 时默认不失败 | `python -m pytest tests/integration/test_rag_api.py -k status` | `V2.1-A2：新增 RAG 状态接口并通过契约测试` |
| V2.1-A3 | 固化 query_knowledge_hub schema | `backend/app/integrations/rag_server/schema.py`、`docs/MCP_SPEC.md`、`tests/unit/test_rag_schema.py` | `StandardRetrievedContext` | 标准输出包含 source_uri、score_type、raw_response_id，文档同步 | `python -m pytest tests/unit/test_rag_schema.py` | `V2.1-A3：固化 RAG 查询标准输出并通过 schema 测试` |
| V2.1-A4 | 实现 source_uri 规则 | `backend/app/integrations/rag_server/mapper.py`、`docs/RAG_SERVER_INTEGRATION.md`、`tests/unit/test_rag_mapper.py` | `build_source_uri` | 缺 doc_id/chunk_id 时生成稳定 fallback 并记录 warning，不伪装为高置信证据 | `python -m pytest tests/unit/test_rag_mapper.py -k source_uri` | `V2.1-A4：实现 source_uri 映射规则并通过映射测试` |
| V2.1-A5 | 增加 rag_trace_log 表 | `backend/app/db/migrations.py`、`backend/app/db/repositories.py`、`tests/integration/test_rag_trace.py` | `RagTraceRepository` | 可写入真实/失败/fallback trace | `python -m pytest tests/integration/test_rag_trace.py` | `V2.1-A5：新增 RAG trace 表并通过持久化测试` |
| V2.1-A6 | 将真实 RAG 调用写 trace | `backend/app/integrations/rag_server/mcp_stdio_client.py`、`backend/app/services/trace_service.py`、`tests/integration/test_rag_server_adapter.py` | `TraceService.record_rag_call` | 每次真实 RAG 调用都有 trace | `python -m pytest tests/integration/test_rag_server_adapter.py -k trace` | `V2.1-A6：接入真实 RAG 调用 trace 并通过集成测试` |
| V2.1-A7 | 实现 list_collections API | `backend/app/api/rag.py`、`tests/integration/test_rag_api.py` | `list_rag_collections` | fake 可回归，真实 RAG 可选 | `python -m pytest tests/integration/test_rag_api.py -k collections` | `V2.1-A7：新增知识库列表接口并通过 API 测试` |
| V2.1-A8 | 实现文档摘要 API | `backend/app/api/rag.py`、`tests/integration/test_rag_api.py` | `get_rag_document_summary` | 路径必须包含 collection | `python -m pytest tests/integration/test_rag_api.py -k summary` | `V2.1-A8：新增文档摘要接口并要求 collection 路径` |
| V2.1-A9 | 增强 timeout/fallback | `backend/app/integrations/rag_server/mcp_stdio_client.py`、`tests/integration/test_rag_server_adapter.py` | `RagServerTimeoutPolicy` | timeout 不伪造引用，写 failure trace | `python -m pytest tests/integration/test_rag_server_adapter.py -k timeout` | `V2.1-A9：增强 RAG 超时降级并通过失败路径测试` |
| V2.1-A10 | real RAG smoke test | `tests/integration/test_rag_server_real_smoke.py` | 无 | 未配置跳过，配置后可调用工具 | `python -m pytest -m rag_server` | `V2.1-A10：新增真实 RAG smoke 测试并保持默认跳过` |
| V2.1-A11 | real eval runner | `backend/app/evaluation/real_rag_runner.py`、`scripts/run_eval.py`、`tests/integration/test_eval_runner.py` | `RealRagEvalRunner` | real eval optional，不阻塞默认检查 | `python -m pytest tests/integration/test_eval_runner.py -k real_rag` | `V2.1-A11：新增真实 RAG 评测入口并保持可选执行` |
| V2.1-A12 | failure category 输出 | `backend/app/evaluation/failure_analysis.py`、`tests/unit/test_eval_metrics.py` | `categorize_failure` | 输出固定失败类别 | `python -m pytest tests/unit/test_eval_metrics.py -k failure` | `V2.1-A12：新增失败类别分析并通过指标测试` |

V2.1 禁止：

- 引入 LangGraph。
- 改写 V1 Agent Workflow。
- 重新实现 ingestion、切片、embedding、向量库或 BM25。
- 默认检查强制依赖真实 RAG-SERVER。

### 6.2 V2.2：Multi-agent Workflow

目标：将 V1 workflow 迁移为 Supervisor + Specialist Agents。

| ID | 小阶段任务 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 | commit 消息示例 |
|---|---|---|---|---|---|---|
| V2.2-B1 | 定义 MultiAgentState | `backend/app/agent/state.py`、`tests/unit/test_multi_agent_state.py` | `MultiAgentState` | 字段与 5.6 一致，agent_trace 可追加 | `python -m pytest tests/unit/test_multi_agent_state.py` | `V2.2-B1：定义多智能体状态并通过状态测试` |
| V2.2-B2 | 新增 agent_trace_log | `backend/app/db/migrations.py`、`backend/app/services/trace_service.py`、`tests/integration/test_trace_api.py` | `AgentTraceRepository` | 可写节点路径、耗时、状态 | `python -m pytest tests/integration/test_trace_api.py -k agent` | `V2.2-B2：新增 Agent trace 持久化并通过接口测试` |
| V2.2-B3 | 实现 Supervisor Agent | `backend/app/agent/supervisor.py`、`tests/unit/test_supervisor_agent.py` | `SupervisorAgent.route` | 中英文畜牧意图基础识别 | `python -m pytest tests/unit/test_supervisor_agent.py` | `V2.2-B3：实现监督智能体路由并通过中英文意图测试` |
| V2.2-B4 | 实现 RAG Agent | `backend/app/agent/rag_agent.py`、`tests/unit/test_rag_agent.py` | `RagAgent.run` | RAG 低置信返回 evidence_status | `python -m pytest tests/unit/test_rag_agent.py` | `V2.2-B4：实现 RAG 智能体并通过证据状态测试` |
| V2.2-B5 | 实现 Disease Agent | `backend/app/agent/disease_agent.py`、`tests/unit/test_disease_agent.py` | `DiseaseAgent.run` | 缺槽追问，信息充分时生成问诊草稿 | `python -m pytest tests/unit/test_disease_agent.py` | `V2.2-B5：实现疾病智能体并通过追问分支测试` |
| V2.2-B6 | 实现 Measurement Agent | `backend/app/agent/measurement_agent.py`、`tests/unit/test_measurement_agent.py` | `MeasurementAgent.run` | 调用体尺分析，不通过 RAG 查询 history | `python -m pytest tests/unit/test_measurement_agent.py` | `V2.2-B6：实现体尺智能体并通过报告测试` |
| V2.2-B7 | 实现 Verifier Agent | `backend/app/agent/verifier_agent.py`、`tests/unit/test_verifier_agent.py` | `VerifierAgent.verify` | unsupported_claim、citation_issues 可检测 | `python -m pytest tests/unit/test_verifier_agent.py` | `V2.2-B7：实现验证智能体并通过证据检查测试` |
| V2.2-B8 | 实现 Safety Agent | `backend/app/agent/safety_agent.py`、`tests/unit/test_safety_agent.py` | `SafetyAgent.check` | 剂量、确定诊断、伪造工具结果被拦截 | `python -m pytest tests/unit/test_safety_agent.py` | `V2.2-B8：实现安全智能体并通过安全测试` |
| V2.2-B9 | 实现 Response Agent | `backend/app/agent/response_agent.py`、`tests/unit/test_response_agent.py` | `ResponseAgent.render` | 使用 safe_answer 和 sources 生成最终回答 | `python -m pytest tests/unit/test_response_agent.py` | `V2.2-B9：实现响应智能体并通过输出测试` |
| V2.2-B10 | 串联 General QA 图 | `backend/app/agent/graph.py`、`tests/integration/test_agent_graph.py` | `run_general_qa_graph` | Supervisor -> RAG -> Verifier -> Safety -> Response | `python -m pytest tests/integration/test_agent_graph.py -k general` | `V2.2-B10：串联通用问答图并通过图测试` |
| V2.2-B11 | 串联疾病问诊图 | `backend/app/agent/graph.py`、`tests/integration/test_agent_graph.py` | `run_disease_graph` | 追问和高风险路径可回归 | `python -m pytest tests/integration/test_agent_graph.py -k disease` | `V2.2-B11：串联疾病问诊图并通过回归测试` |
| V2.2-B12 | 串联体尺报告图 | `backend/app/agent/graph.py`、`tests/integration/test_agent_graph.py` | `run_measurement_graph` | 体尺 workflow 回归通过 | `python -m pytest tests/integration/test_agent_graph.py -k measurement` | `V2.2-B12：串联体尺报告图并通过回归测试` |

V2.2 验收：

- Safety Agent 是最终输出前必经节点。
- V1 三条业务闭环继续通过。
- fake eval 继续通过。
- Agent trace 完整记录节点路径、耗时和状态。

### 6.3 V2.3：前端 UI 与 Debug Panel

目标：不依赖 Swagger，能面试演示。

| ID | 小阶段任务 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 | commit 消息示例 |
|---|---|---|---|---|---|---|
| V2.3-C1 | 建立静态前端入口 | `backend/app/static/frontend/index.html`、`backend/app/static/frontend/app.js`、`backend/app/static/frontend/styles.css`、`backend/app/main.py`、`docs/FRONTEND_SPEC.md` | `mount_frontend` | 通过 FastAPI 静态路由访问，不新增 Node 依赖 | `python scripts/check_v2.py --frontend-contract` | `V2.3-C1：建立静态前端入口并通过契约检查` |
| V2.3-C2 | 实现 Chat Page | `backend/app/static/frontend/index.html`、`backend/app/static/frontend/app.js`、`tests/integration/test_frontend_contract.py` | `renderChat`、`submitChat` | 能提问、展示 answer/intent/risk_level | `python -m pytest tests/integration/test_frontend_contract.py -k chat` | `V2.3-C2：实现聊天页面并通过前端契约测试` |
| V2.3-C3 | 展示引用和工具摘要 | `backend/app/static/frontend/app.js`、`backend/app/static/frontend/styles.css` | `renderSources`、`renderToolSummary` | 展示 source_uri、title、page、tools_used | `python -m pytest tests/integration/test_frontend_contract.py -k sources` | `V2.3-C3：展示引用和工具摘要并通过契约测试` |
| V2.3-C4 | 实现 Measurement Page | `backend/app/static/frontend/index.html`、`backend/app/static/frontend/app.js` | `renderMeasurement`、`submitMeasurement` | 可输入体尺并展示报告/evidence | `python -m pytest tests/integration/test_frontend_contract.py -k measurement` | `V2.3-C4：实现体尺页面并通过契约测试` |
| V2.3-C5 | 实现 Debug JSON Panel | `backend/app/static/frontend/app.js`、`backend/app/static/frontend/styles.css` | `renderDebugPanel` | 展示 request_id、rag_mode、agent_path、safety/verifier | `python -m pytest tests/integration/test_frontend_contract.py -k debug` | `V2.3-C5：新增调试面板并展示核心 trace 字段` |
| V2.3-C6 | 前端 smoke test | `tests/e2e/test_frontend_smoke.py` | 无 | 静态页面、Chat、Measurement 基础渲染通过 | `python -m pytest tests/e2e/test_frontend_smoke.py` | `V2.3-C6：补充前端冒烟测试并通过演示验证` |

前端设计约束：

- 不做完整文档管理后台。
- 不做复杂权限系统。
- 不要求后端改变统一响应格式。
- Debug Panel 可以简陋，但字段必须完整。
- 不引入 React/Vite/Node 构建链；如后续确实需要，必须新增单独决策任务并更新 `docs/FRONTEND_SPEC.md`。

### 6.4 V2.4：Session Context 多轮追问

目标：疾病问诊可续接上下文，但不污染安全判断。

| ID | 小阶段任务 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 | commit 消息示例 |
|---|---|---|---|---|---|---|
| V2.4-D1 | 新增 session_context 表 | `backend/app/db/migrations.py`、`tests/integration/test_session_context.py` | migration | 表结构与设计一致 | `python -m pytest tests/integration/test_session_context.py -k schema` | `V2.4-D1：新增会话上下文表并通过迁移测试` |
| V2.4-D2 | 实现 SessionContextService | `backend/app/services/session_context_service.py`、`tests/unit/test_session_context.py` | `SessionContextService` | 保存/读取/更新上下文 | `python -m pytest tests/unit/test_session_context.py -k service` | `V2.4-D2：实现会话上下文服务并通过单元测试` |
| V2.4-D3 | 实现 slot_sources | `backend/app/services/session_context_service.py`、`tests/unit/test_session_context.py` | `SlotSource` | 支持 user_confirmed/ai_inferred/missing/stale/tool_result，非法值拒绝 | `python -m pytest tests/unit/test_session_context.py -k slot_sources` | `V2.4-D3：实现槽位来源标记并通过测试` |
| V2.4-D4 | 实现 TTL 和 stale | `backend/app/services/session_context_service.py`、`tests/unit/test_session_context.py` | `expire_stale_context` | 疾病 pending slots 2 小时，QA/体尺 24 小时，高风险等级不自动复用 | `python -m pytest tests/unit/test_session_context.py -k ttl` | `V2.4-D4：实现上下文过期机制并通过 TTL 测试` |
| V2.4-D5 | 接入疾病追问 workflow | `backend/app/agent/graph.py`、`tests/e2e/test_session_follow_up_flow.py` | `merge_session_slots` | 第二轮可续接第一轮缺槽 | `python -m pytest tests/e2e/test_session_follow_up_flow.py` | `V2.4-D5：接入多轮追问上下文并通过 E2E 测试` |
| V2.4-D6 | 处理用户否定和换动物 | `backend/app/services/session_context_service.py`、`tests/e2e/test_session_follow_up_flow.py` | `clear_conflicted_context` | 否定/换动物后清理上下文 | `python -m pytest tests/e2e/test_session_follow_up_flow.py -k reset` | `V2.4-D6：处理上下文重置并通过否定场景测试` |

### 6.5 V2.5：真实评测报告与交付材料

目标：能说明真实 RAG-SERVER 的质量瓶颈，并形成面试材料。

| ID | 小阶段任务 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 | commit 消息示例 |
|---|---|---|---|---|---|---|
| V2.5-E1 | 新增 eval_run_log 表 | `backend/app/db/migrations.py`、`tests/integration/test_eval_runner.py` | `EvalRunRepository` | eval run 可记录 metrics/failure summary | `python -m pytest tests/integration/test_eval_runner.py -k log` | `V2.5-E1：新增评测运行日志并通过持久化测试` |
| V2.5-E2 | 生成 real RAG 失败分析 | `backend/app/evaluation/failure_analysis.py`、`reports/` | `build_failure_report` | 输出失败类别统计和样例 | `python scripts/run_eval.py --mode real --optional` | `V2.5-E2：生成真实 RAG 失败分析报告` |
| V2.5-E3 | 增加 multi-agent eval | `backend/app/evaluation/multi_agent_runner.py`、`tests/integration/test_eval_runner.py` | `MultiAgentEvalRunner` | 路由、路径、安全、trace 指标可计算 | `python -m pytest tests/integration/test_eval_runner.py -k multi_agent` | `V2.5-E3：新增多智能体评测并通过指标测试` |
| V2.5-E4 | 更新 V2 README | `README.md`、`docs/INTERVIEW_NOTES.md` | 无 | 说明架构、演示步骤和真实 RAG 限制 | 人工检查 + `python scripts/check_v2.py --docs` | `V2.5-E4：更新 V2 说明文档和面试讲解稿` |
| V2.5-E5 | 编写 demo script | `docs/DEMO_SCRIPT.md` | 无 | 覆盖 Chat、疾病问诊、体尺报告、Debug Panel | 人工演练 | `V2.5-E5：编写演示脚本并覆盖三条业务闭环` |

### 6.6 进度跟踪表

| 阶段 | 目标 | 状态 | 主要验收命令 |
|---|---|---|---|
| V2.1 | 真实 RAG-SERVER 接入与验收 | IN_PROGRESS（A0-A10 已完成） | `python -m pytest tests/integration/test_rag_server_adapter.py` |
| V2.2 | Multi-agent Workflow | TODO | `python -m pytest tests/integration/test_agent_graph.py` |
| V2.3 | 前端 UI 与 Debug Panel | TODO | `python -m pytest tests/integration/test_frontend_contract.py` |
| V2.4 | Session Context 多轮追问 | TODO | `python -m pytest tests/e2e/test_session_follow_up_flow.py` |
| V2.5 | 真实评测和交付材料 | TODO | `python scripts/run_eval.py --mode fake` |

### 6.7 每次小阶段完成检查清单

- 是否仍然没有重写 RAG-SERVER 底层能力。
- 是否使用当前项目 `.venv` 运行命令。
- 是否运行当前任务指定测试。
- 是否运行必要 V1 回归。
- 是否保持 fake eval 通过。
- 是否保持 Safety tests 通过。
- 是否更新相关 docs / spec。
- 是否没有提交 `.venv/`、真实密钥、临时日志、大型运行数据。
- 是否用简体中文 commit 消息完成提交。
- commit 是否只包含当前小阶段相关改动。

---

## 7. Code Agent / Subagent 约束

### 7.1 V2.1 约束

```text
本轮开发只允许做 RAG-SERVER 产品级接入。
禁止引入 LangGraph。
禁止改写 V1 Agent Workflow。
禁止修改 Safety 禁止规则。
禁止实现 LoRA。
禁止做复杂前端。
禁止重新实现 ingestion、切片、embedding、向量库或 BM25。
```

必须保证：

```text
pytest tests/ 全部通过。
fake eval 继续通过。
未配置 RAG_SERVER_PATH 时默认检查不失败。
配置 RAG_SERVER_PATH 时 real smoke test 可运行。
RAG-SERVER 失败时不伪造引用。
所有真实 RAG 调用都写入 rag_trace_log。
source_uri 作为引用、Verifier、Trace、Eval 的稳定来源 ID。
```

### 7.2 V2.2 约束

```text
本轮开发只允许实现 Multi-agent Workflow。
Safety Agent 必须是最终输出前必经节点。
不得修改 RAG-SERVER adapter 已有 schema。
不得放开具体药物剂量或确定性诊断。
不得破坏 V1 三条业务闭环。
```

### 7.3 V2.3 约束

```text
本轮开发只做前端可演示闭环。
优先 Chat Page、Measurement Page、引用展示、工具摘要、Debug JSON Panel。
不做完整文档管理后台。
不做复杂权限系统。
前端必须遵守 `docs/API_SPEC.md` 和 `docs/FRONTEND_SPEC.md`。
```

---

## 8. V2 总体验收标准

完成 V2 后应满足：

1. V2.1-V2.5 分阶段交付，不一次性大重构。
2. 真实 RAG-SERVER 有 schema、trace、timeout、fallback 和 real eval。
3. V2.1 不动 V1 workflow，V2.2 再引入 Multi-agent。
4. Safety Agent / Final Safety Guard 仍是最终输出硬约束。
5. Session Context 有 TTL、slot_sources 和 stale 机制。
6. Verifier Agent 有明确 JSON 输出和证据支持边界。
7. fake eval 做回归，real eval 做真实质量验证。
8. Chat、Measurement 和 Debug Panel 足够面试展示。
9. V2 Harness 能限制 subagent 改动范围。
10. 每个 V2 小阶段都有测试、文档和简体中文 commit。
11. demo / real eval 模式禁止静默降级到 fake。
12. 引用、Verifier、Trace、Eval 均使用 `source_uri` 作为来源 ID。
13. V2.1 只验收既有 ingestion proxy / dry-run，不重新实现 RAG ingestion。
