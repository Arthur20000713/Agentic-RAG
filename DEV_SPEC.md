# DEV_SPEC：畜牧业 Agentic RAG 系统开发规范（RAG-SERVER 集成版）

> 版本：V1 集成版初稿  
> 设计来源：`README.md`、`AGENTS.md`  
> 关键前提：`RAG-SERVER` 是已完成的独立 RAG 系统，当前项目只做接入与畜牧 Agent 应用层开发  
> 默认约束：Python、pytest、本地优先、轻量级、默认测试零外部服务依赖

本文档用于指导当前项目从规格到开发落地。本版明确：**不要在当前项目中重新开发文档解析、切片、embedding、向量库、BM25、混合检索、rerank、引用生成、RAG Dashboard 或 RAG 评测框架**。这些能力已经由你自己开发的 `RAG-SERVER` 提供。关于`RAG-SERVER` 的信息可以在当前根目录下的 `AGENTS.md` 中获取

当前项目的职责是：

- 面向畜牧业场景实现 API、Agent Workflow、疾病安全规则、体尺分析、评测和应用层交互。
- 通过本地适配器接入 `RAG-SERVER` 的 MCP stdio 服务和 CLI。
- 将 `RAG-SERVER` 的通用知识库能力包装为畜牧领域工具，如 `livestock_rag_search`。
- 在默认测试中使用 fake client，不要求启动真实 `RAG-SERVER`；真实接入测试单独标记并可跳过。

---

## 1. 项目概述

### 1.1 设计理念

| 原则 | 说明 |
|---|---|
| 复用既有 RAG，不重复造轮子 | `RAG-SERVER` 已实现 ingestion、hybrid retrieval、rerank、citation、MCP、Dashboard，本项目只做应用层集成。 |
| 先闭环，后扩展 | V1 先完成文档问答、疾病问诊、体尺报告三条闭环。 |
| 先规则，后模型 | 疾病风险、安全拒答、体尺异常判断优先用可测试规则实现。 |
| 先契约，后实现 | API、RAG-SERVER adapter、MCP wrapper、AgentState、错误码、日志字段先稳定。 |
| 本地优先 | 默认开发和测试不依赖云端 API、远程数据库、远程向量库或真实模型服务。 |
| 工具失败诚实降级 | RAG-SERVER 未启动、超时或返回错误时，不伪造检索结果和引用。 |
| 最终输出必过安全检查 | 疾病、用药、疫情、食品安全相关回答在最终返回前必须经过 Final Safety Guard。 |

### 1.2 项目定位

项目名称：

```text
基于 MCP 的畜牧业 Agentic RAG 智能问答与决策辅助系统
```

系统定位：

- 当前项目是畜牧业 Agent 应用层。
- `RAG-SERVER` 是后续接入的本地知识库/RAG 能力层。
- 系统提供文档可追溯问答、疾病问诊前信息整理、体尺结构化分析。
- 系统只做辅助决策，不替代兽医诊断，不直接开具处方。
- V1 阶段一律不输出具体药物剂量。

### 1.3 V1 业务边界

V1 必做：

1. 文档问答闭环：用户提问 -> Agent 路由 -> 调用 `RAG-SERVER` -> 生成带引用回答。
2. 疾病问诊闭环：意图识别 -> 槽位抽取 -> 规则风险评估 -> RAG-SERVER 检索依据 -> 安全回答。
3. 体尺报告闭环：输入体尺数据 -> 查询本项目 SQLite 历史或 demo 历史 -> 规则分析 -> 结构化报告。
4. RAG-SERVER 接入层：实现 fake / CLI / MCP stdio 三类 client 或 gateway，默认 fake，真实接入可选。
5. MCP wrapper：将 RAG-SERVER 能力包装为本项目工具 `livestock_rag_search`、`get_source_detail`，并实现领域工具 `disease_risk_evaluator`、`body_measurement_analyzer`。
6. 评测闭环：基于 pytest 和 golden set 评估意图、引用、安全、追问、体尺结构完整性。

V1 不做：

- 不重写 RAG-SERVER 的 parser、splitter、embedding、vector store、BM25、reranker、response builder。
- 不在当前项目维护 chunk 表或向量索引。
- 不直接修改 `C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER`，除非后续用户明确提出。
- 不复制或暴露 RAG-SERVER `config/settings.yaml` 中的真实 API key。
- 不默认依赖真实 RAG-SERVER 进程通过全部测试。
- 不实现 LoRA、强 Multi-agent、长期记忆、复杂养殖日报或完整管理后台。

### 1.4 成功标准

| 维度 | 成功标准 |
|---|---|
| 可开发 | code agent 能按阶段实现，不会被诱导重写 RAG-SERVER。 |
| 可测试 | 默认 `pytest` 使用 fake RAG client，不需要网络、API key 或真实 RAG-SERVER。 |
| 可接入 | 设置 `RAG_SERVER_PATH` 后，可以通过 CLI 或 MCP stdio 调用真实 RAG-SERVER。 |
| 可演示 | 能演示文档问答、疾病问诊、体尺报告三条主线。 |
| 可评测 | 能输出 golden set 的 JSON / CSV / summary 评测结果。 |
| 可维护 | API、adapter、工具 schema、安全规则和日志字段有契约测试。 |

---

## 2. 核心特点

| 核心特点 | 简要说明 |
|---|---|
| RAG-SERVER 复用 | 当前项目复用已有 RAG-SERVER 的 ingestion、hybrid retrieval、rerank、citation、MCP 能力。 |
| 适配器隔离 | 通过 `RagServerClient` 抽象屏蔽 fake、CLI、MCP stdio 的差异，Agent 不直接依赖外部命令细节。 |
| MCP wrapper | 将 RAG-SERVER 的 `query_knowledge_hub`、`get_document_summary` 等能力包装为畜牧领域工具。 |
| Agentic Workflow | 用轻量状态机完成意图识别、槽位抽取、工具路由、安全校验、Verifier-lite 和最终回答。 |
| 垂直安全控制 | 对疾病诊断、用药、剂量、疫情、群体发病等问题进行硬性安全检查。 |
| 体尺报告差异化 | 当前项目保留体尺数据、历史查询和结构化报告能力，异常结论必须有数值依据。 |
| 本地优先测试 | 默认使用 fake RAG 结果和 SQLite 临时库，真实 RAG-SERVER 测试单独标记。 |
| Harness 约束开发 | 用 DEV_SPEC、API/MCP/Safety 契约、pytest 和一键检查脚本约束 Code Agent / vibe coding。 |

---

## 3. 技术选型

### 3.1 V1 默认技术栈

| 模块 | V1 默认选型 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | 当前项目应用层开发。 |
| Web API | FastAPI | 提供 chat、measurement、document ingest proxy、task 查询接口。 |
| 数据校验 | Pydantic | API schema、AgentState、RAG adapter schema、MCP wrapper schema。 |
| 配置 | PyYAML + Pydantic Settings | `config/settings.yaml`；测试使用 `config/settings.test.yaml`。 |
| 应用数据库 | SQLite | 只保存动物档案、体尺记录、会话日志、工具日志、RAG ingestion proxy 任务。 |
| RAG 能力 | 既有 `RAG-SERVER` | 通过 MCP stdio 或 CLI 接入，不在当前项目重写。 |
| RAG 测试替身 | `FakeRagServerClient` | 默认测试使用固定夹具，保证无外部依赖。 |
| LLM | `TemplateLLM` / 可选本地模型接口 | 默认模板生成，真实模型不作为测试必需依赖。 |
| Agent | 自研轻量状态机 | V1 不上 LangGraph。 |
| MCP | 当前项目 MCP wrapper + RAG-SERVER MCP client | 当前项目包装畜牧工具；RAG-SERVER 提供底层知识库工具。 |
| 测试 | pytest | 单元、集成、E2E、评测 runner。 |

### 3.2 RAG-SERVER 现有能力

根据 `AGENTS.md`，RAG-SERVER 已提供：

| 能力 | RAG-SERVER 入口或模块 | 当前项目使用方式 |
|---|---|---|
| 文档 ingestion | `scripts/ingest.py`、`src/ingestion/pipeline.py` | 由 `RagServerCliGateway.ingest()` 调用。 |
| 查询 | MCP tool `query_knowledge_hub`、`src/core/query_engine/hybrid_search.py` | V1 真实查询优先通过 MCP stdio；CLI query 只允许人工调试，不作为默认 adapter。 |
| MCP stdio server | `python -m src.mcp_server.server` | `RagServerMcpClient` 启动子进程并调用 tools。 |
| MCP query tool | `query_knowledge_hub` | 映射为 `livestock_rag_search`。 |
| collection 列表 | `list_collections` | 用于健康检查和调试。 |
| 文档摘要 | `get_document_summary` | 映射为 `get_source_detail` 的可用 fallback。 |
| 引用和多模态响应 | `src/core/response/*` | 当前项目只消费结果，不重建引用生成器。 |
| 评测 | `scripts/evaluate.py` | 可作为 RAG 层独立评测，不代替当前 Agent 评测。 |
| Dashboard | Streamlit dashboard | 当前项目不重做。 |

注意：

- RAG-SERVER 真正 MCP 入口是 `python -m src.mcp_server.server`。
- 不要假设 `mcp-server` console script 能启动真实 MCP server。
- RAG-SERVER stdio 的 stdout 保留给 JSON-RPC，日志必须在 stderr；当前项目的 MCP client 不得污染其 stdout。

### 3.3 依赖原则

- 当前项目默认测试不得要求网络、API key、远程数据库、GPU 或真实 RAG-SERVER 进程。
- 真实 RAG-SERVER 集成测试必须用 marker，例如 `@pytest.mark.rag_server`，未设置 `RAG_SERVER_PATH` 时跳过。
- 当前项目不得复制 RAG-SERVER 中的真实密钥或配置敏感值。
- 当前项目不得把模拟体尺历史写入正式 `body_measurement_record`。
- 当前项目不得在业务逻辑中直接 shell 调用 RAG-SERVER；必须经过 `RagServerClient` 或 gateway 抽象。
- RAG-SERVER 路径解析优先级固定为：环境变量 `RAG_SERVER_PATH` > `settings.yaml` 的 `rag_server.repo_path`；相对路径一律相对当前项目根目录解析。
- V1 查询模式只允许 `fake` 或 `mcp_stdio`；CLI 只用于 ingestion 代理，不从 CLI stdout 推断 hits、score 或 citations。

### 3.4 本地虚拟环境规范

当前项目必须使用项目根目录下的 `.venv` 作为全程开发和测试环境。后续 code agent 执行安装、测试、脚本、评测时，都应默认使用当前项目 `.venv` 中的 Python，不使用系统 Python 直接运行。

Windows PowerShell 初始化命令：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest -m "not rag_server"
```

若 `pyproject.toml` 还未定义 `dev` extra，A 阶段应先补齐最小依赖声明，再执行安装。V1 最小开发依赖至少包括：

```text
fastapi
uvicorn
pydantic
pyyaml
pytest
pytest-asyncio
```

虚拟环境规则：

- `.venv/` 必须加入 `.gitignore`，不得提交到版本库。
- `scripts/check_all.py`、`scripts/query.py`、`scripts/ingest_via_rag_server.py` 文档示例均使用 `python -m ...` 风格，确保走当前激活环境。
- 当前项目使用自己的 `.venv`；`RAG-SERVER` 作为独立 sibling 项目，可以使用它自己的环境。
- 当前项目不得把 RAG-SERVER 的依赖整体复制进自己的 `pyproject.toml`，只声明 adapter、API、Agent、测试所需依赖。
- 调用真实 RAG-SERVER 时，优先使用 `rag_server.python_executable` 配置指定 RAG-SERVER 的 Python；未配置时才使用当前 `.venv` 的 Python。
- 默认测试仍然使用 `rag_server.query_mode=fake`，创建 `.venv` 不意味着必须安装或启动真实 RAG-SERVER。

---

## 4. 测试方案

### 4.1 TDD 理念

每个增量遵循：

```text
写失败测试 -> 实现最小代码 -> 跑通测试 -> 必要时重构 -> 更新契约文档
```

要求：

- 新功能先写至少一个测试。
- RAG-SERVER 集成先写 fake client contract test，再接真实 MCP / CLI。
- 不为 V2/V3 写兼容代码。
- 不把真实 RAG-SERVER 是否安装作为默认测试通过条件。

### 4.2 分层测试

```text
tests/
├── unit/
│   ├── test_config.py
│   ├── test_response.py
│   ├── test_schemas.py
│   ├── test_rag_server_mapper.py
│   ├── test_fake_rag_server_client.py
│   ├── test_template_client.py
│   ├── test_answer_generator.py
│   ├── test_disease_risk.py
│   ├── test_measurement_analyzer.py
│   ├── test_safety.py
│   ├── test_agent_router.py
│   └── test_verifier.py
├── integration/
│   ├── test_rag_server_client_contract.py
│   ├── test_rag_server_cli_gateway.py
│   ├── test_rag_server_mcp_client.py
│   ├── test_mcp_tools.py
│   ├── test_api_contract.py
│   ├── test_tool_timeout.py
│   ├── test_agent_workflow.py
│   ├── test_sqlite_schema.py
│   └── test_cli_scripts.py
├── e2e/
│   ├── test_document_qa_flow.py
│   ├── test_disease_consultation_flow.py
│   └── test_measurement_report_flow.py
└── fixtures/
    ├── rag_server/
    │   ├── query_response.json
    │   ├── low_confidence_response.json
    │   └── document_summary.json
    ├── golden_set.json
    ├── measurement_history.json
    └── disease_cases.json
```

| 测试层级 | 范围 | 默认是否需要真实 RAG-SERVER | 命令 |
|---|---|---:|---|
| 单元测试 | schema、mapper、规则、fake client、answer generator | 否 | `pytest tests/unit` |
| 集成测试 | API、MCP wrapper、Agent workflow、SQLite、RAG client contract | 否，默认 fake | `pytest tests/integration` |
| 真实 RAG-SERVER 测试 | MCP stdio / CLI 真实调用 | 是，缺配置跳过 | `pytest -m rag_server` |
| E2E 测试 | 三条业务闭环 | 否，默认 fake | `pytest tests/e2e` |
| 评测 | golden set runner | 否，默认 fake；可选真实 RAG | `python scripts/run_eval.py` |

### 4.3 必测契约

| 契约 | 测试文件 | 必须检查 |
|---|---|---|
| API 响应 | `tests/integration/test_api_contract.py` | 所有接口包含 `code`、`message`、`data`、`request_id`。 |
| RAG adapter | `tests/integration/test_rag_server_client_contract.py` | fake / CLI / MCP client 返回统一 `RagSearchResult`。 |
| RAG mapper | `tests/unit/test_rag_server_mapper.py` | RAG-SERVER MCP content 能映射为 chunks、sources、citations。 |
| MCP wrapper | `tests/integration/test_mcp_tools.py` | `livestock_rag_search` 等工具 schema、错误码、超时降级。 |
| Safety | `tests/unit/test_safety.py` | 不输出剂量、不确定诊断、高风险提示兽医、工具失败不伪造。 |
| 体尺报告 | `tests/unit/test_measurement_analyzer.py` | 无历史不判断趋势，异常必须有数值证据。 |
| 多轮追问 | `tests/e2e/test_disease_consultation_flow.py` | 关键信息缺失时追问，且不超过 3 个问题。 |

### 4.4 Agent 性能评估

V1 先使用 60 条黄金评测集：

| 类型 | 数量 |
|---|---:|
| 普通知识问答 | 10 |
| 疾病问诊 | 15 |
| 饲养管理 | 10 |
| 体尺解释 | 10 |
| 高风险拒答 | 10 |
| 无答案问题 | 5 |

评测指标：

| 指标 | 说明 |
|---|---|
| Intent Accuracy | 意图识别准确率。 |
| RAG Call Accuracy | 需要检索时是否调用 RAG-SERVER adapter。 |
| Citation Coverage | 专业回答是否带引用。 |
| No-answer Accuracy | RAG 低置信或无结果时是否拒答。 |
| Safety Pass Rate | 是否通过安全规则。 |
| Structure Completeness | 疾病问诊和体尺报告结构是否完整。 |
| Follow-up Trigger Accuracy | 应该追问时是否触发追问。 |
| Tool Failure Honesty | RAG-SERVER 失败时是否明确说明失败且不伪造结果。 |

输出：

```text
reports/eval_result.json
reports/eval_result.csv
reports/eval_summary.md
```

### 4.5 验收门槛

- 默认单元测试、集成测试、E2E 测试通过率 100%。
- `pytest -m "not rag_server"` 不需要真实 RAG-SERVER。
- Safety Pass Rate 100%。
- Must Not Include Violation 为 0。
- 工具失败诚实率 100%。
- 专业 RAG 回答引用覆盖率不低于 90%。

---

## 5. 系统架构与模块设计

### 5.1 整体架构图

```text
+-----------------------------+
| Client / CLI / Local Web UI  |
+--------------+--------------+
               |
               v
+-----------------------------+
| FastAPI API Layer            |
| - unified response           |
| - request validation         |
| - error mapping              |
+--------------+--------------+
               |
               v
+-----------------------------+
| Agent Controller             |
| - Intent Router              |
| - Slot Extractor             |
| - Tool Caller                |
| - Verifier-lite              |
| - Final Safety Guard         |
+----+-------------------+----+
     |                   |
     v                   v
+----------------+   +----------------------+
| Domain Tools   |   | Domain Rule Layer    |
| - rag wrapper  |   | - disease risk       |
| - source       |   | - safety rules       |
| - measurement  |   | - measurement rules  |
+-------+--------+   +----------+-----------+
        |                       |
        v                       v
+------------------------------------------------+
| Current Project Local Services                  |
| - RagServerClient abstraction                   |
| - MeasurementService + SQLite                   |
| - TemplateLLM / AnswerGenerator                 |
| - Eval runner                                   |
+---------------------+--------------------------+
                      |
                      v
+------------------------------------------------+
| Existing RAG-SERVER (local sibling project)      |
| - MCP stdio: python -m src.mcp_server.server     |
| - CLI: scripts/ingest.py / query.py / evaluate.py|
| - ChromaDB + BM25 + image index                  |
| - Hybrid search + rerank + citations             |
+------------------------------------------------+
```

### 5.2 完整目录结构树

```text
livestock-agentic-rag/
├── README.md
├── AGENTS.md
├── DEV_SPEC.md
├── pyproject.toml
├── config/
│   ├── settings.yaml
│   └── settings.test.yaml
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── chat.py
│       │   ├── documents.py
│       │   ├── tasks.py
│       │   └── measurement.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── errors.py
│       │   ├── logging.py
│       │   └── response.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── agent.py
│       │   ├── document.py
│       │   ├── measurement.py
│       │   ├── mcp.py
│       │   └── rag_server.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── connection.py
│       │   ├── migrations.py
│       │   └── repositories.py
│       ├── integrations/
│       │   └── rag_server/
│       │       ├── __init__.py
│       │       ├── base.py
│       │       ├── fake_client.py
│       │       ├── cli_gateway.py
│       │       ├── mcp_stdio_client.py
│       │       ├── mapper.py
│       │       └── health.py
│       ├── mcp_server/
│       │   ├── __init__.py
│       │   └── tools.py
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── router.py
│       │   ├── extractor.py
│       │   ├── tool_caller.py
│       │   ├── workflow.py
│       │   ├── safety.py
│       │   └── verifier.py
│       ├── model/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── template_client.py
│       ├── rules/
│       │   ├── disease_risk.yaml
│       │   ├── safety_rules.yaml
│       │   └── measurement_rules.yaml
│       ├── services/
│       │   ├── __init__.py
│       │   ├── chat_service.py
│       │   ├── document_service.py
│       │   ├── measurement_service.py
│       │   └── task_service.py
│       └── evaluation/
│           ├── __init__.py
│           ├── golden_runner.py
│           └── metrics.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
├── scripts/
│   ├── query.py
│   ├── ingest_via_rag_server.py
│   ├── run_eval.py
│   └── check_all.py
├── data/
│   ├── local/
│   ├── uploads/
│   └── demo/
├── logs/
├── reports/
└── docs/
    ├── API_SPEC.md
    ├── MCP_SPEC.md
    ├── RAG_SERVER_INTEGRATION.md
    ├── SAFETY_SPEC.md
    ├── EVAL_SPEC.md
    └── HARNESS.md
```

V1 约定：

- 当前项目不创建 `backend/app/rag/parser.py`、`splitter.py`、`embedder.py`、`vector_store.py`、`retriever.py`。
- 所有测试统一放根目录 `tests/`。
- RAG-SERVER 的路径通过配置读取，不硬编码到业务逻辑。

### 5.3 模块职责说明表

| 模块 | 主要文件 | 职责 | 禁止事项 |
|---|---|---|---|
| API 层 | `backend/app/api/*.py` | 请求校验、调用 service、返回统一响应。 | 不直接调用 shell 或 RAG-SERVER。 |
| Core | `backend/app/core/*.py` | 配置、错误码、日志、统一响应。 | 不依赖业务模块。 |
| Schemas | `backend/app/schemas/*.py` | Pydantic 契约。 | 不写业务逻辑。 |
| DB | `backend/app/db/*.py` | SQLite 连接、应用表初始化、repository。 | 不保存 RAG chunk 或向量。 |
| RAG-SERVER 集成 | `backend/app/integrations/rag_server/*.py` | fake/CLI/MCP client、结果映射、健康检查。 | 不复制 RAG-SERVER 内部实现。 |
| MCP wrapper | `backend/app/mcp_server/*.py` | 包装领域 Tools。V1 不实现 Resource/Prompt，留到 V1.1。 | 不增加写入型工具。 |
| Agent | `backend/app/agent/*.py` | 状态机编排、路由、槽位抽取、安全、校验。 | 不直接访问 RAG-SERVER 进程。 |
| Model | `backend/app/model/*.py` | 模板生成和可选模型接口。 | 不把 API key 写入代码。 |
| Rules | `backend/app/rules/*` | 疾病风险、安全规则、体尺规则。 | 不把安全规则只写进 prompt。 |
| Services | `backend/app/services/*.py` | 组合 repository、RAG adapter、Agent。 | 不绕过 Final Safety Guard。 |
| Evaluation | `backend/app/evaluation/*.py` | golden set runner、指标计算。 | 默认不依赖真实 RAG-SERVER。 |

### 5.4 数据流说明

#### 5.4.1 文档入库与索引

当前项目不解析文档，只代理到 RAG-SERVER：

```text
POST /api/documents/upload
  -> DocumentService 保存上传文件到 data/uploads
  -> TaskService 创建 rag_ingestion_task(status=pending)
  -> 返回 task_id

POST /api/tasks/{task_id}/index
  -> TaskService 将任务状态置为 running
  -> 同步调用 RagServerCliGateway.ingest(path, collection)
  -> RAG-SERVER scripts/ingest.py
  -> RAG-SERVER 完成解析、切片、embedding、Chroma/BM25 写入
  -> TaskService 记录 status / stdout / stderr / exit_code / finished_at
```

约束：

- 当前项目只保存上传记录和任务状态，不保存 chunk 正文和向量。
- `--dry-run` 可用于接入验证。
- RAG-SERVER ingestion 失败时，当前项目只记录失败，不尝试自行解析。
- V1 采用同步执行模型：`POST /api/tasks/{task_id}/index` 在请求内完成一次 ingestion 代理调用并返回最终状态；后台任务、队列和并发 worker 放到 V1.1。

#### 5.4.2 文档问答

```text
POST /api/chat
  -> ChatService.ask
  -> AgentWorkflow.run
  -> IntentRouter: general_qa
  -> ToolCaller.call(livestock_rag_search)
  -> RagServerClient.query(query, top_k, collection)
  -> RAG-SERVER query_knowledge_hub
  -> RagServerMapper.to_retrieved_contexts
  -> AnswerGenerator.compose_with_citations
  -> VerifierLite
  -> FinalSafetyGuard
  -> ApiResponse.success
```

约束：

- RAG-SERVER 返回低置信、空结果或调用失败时，必须走无答案策略。
- 专业结论必须带引用。
- fake client 的返回结构必须与真实 client 的标准化结果一致。
- `AnswerGenerator` 只做应用层答案拼装，citations 必须来自 `RagSearchResult.citations` 或 `RagSource`，不得重新推断页码、章节或来源。

#### 5.4.3 疾病问诊

```text
POST /api/chat
  -> Router: disease_consultation
  -> SlotExtractor
  -> MissingInfoPolicy
  -> disease_risk_evaluator
  -> livestock_rag_search
  -> DraftAnswer
  -> SafetyGuard
  -> VerifierLite
  -> FinalSafetyGuard
```

约束：

- 缺少关键信息时最多追问 3 个问题。
- `disease_risk_evaluator` 不调用 LLM，不调用 RAG-SERVER。
- 疾病类回答末尾必须包含兽医确认提示。
- V1 不输出具体药物剂量。

#### 5.4.4 体尺报告

```text
POST /api/measurement/analyze
  -> MeasurementService.load_history_from_sqlite
  -> BodyMeasurementAnalyzer
  -> Optional livestock_rag_search for metric definitions
  -> ReportGenerator
  -> VerifierLite
  -> FinalSafetyGuard
```

约束：

- 体尺历史数据属于当前项目 SQLite，不属于 RAG-SERVER。
- 无历史数据时不能判断增长趋势。
- 使用 demo history 时，报告必须显式标注演示数据。
- 异常结论必须有数值依据。

### 5.5 配置驱动设计示例

```yaml
app:
  name: "livestock-agentic-rag"
  env: "local"
  debug: true

storage:
  sqlite_path: "data/local/app.db"
  upload_dir: "data/uploads"

rag_server:
  query_mode: "fake"  # fake | mcp_stdio
  ingest_mode: "cli"  # cli
  repo_path: "../RAG-SERVER"
  python_executable: "python"
  config_path: "config/settings.yaml"
  default_collection: "default"
  query_timeout_ms: 5000
  ingest_timeout_ms: 60000
  mcp_command:
    - "python"
    - "-m"
    - "src.mcp_server.server"

safety:
  block_drug_dosage: true
  require_vet_disclaimer: true
  max_follow_up_questions: 3

evaluation:
  golden_set_path: "tests/fixtures/golden_set.json"
  output_dir: "reports"
```

配置规则：

- `settings.test.yaml` 必须设置 `rag_server.query_mode: fake`。
- `rag_server.query_mode: mcp_stdio` 只能通过 `RagServerMcpClient` 启动 `python -m src.mcp_server.server`。
- `rag_server.ingest_mode: cli` 只能通过 `RagServerCliGateway` 调用 RAG-SERVER `scripts/ingest.py`。
- RAG-SERVER 路径解析优先级固定为：`RAG_SERVER_PATH` 环境变量 > `rag_server.repo_path`。
- `rag_server.repo_path` 为相对路径时，一律相对当前项目根目录解析。
- 不允许在业务代码中写死 `C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER`。

### 5.6 V1 契约定义

#### 5.6.1 统一 API 响应

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "req_001"
}
```

错误码：

| code | 含义 |
|---:|---|
| 0 | 成功 |
| 40001 | 请求参数错误 |
| 40004 | 资源不存在 |
| 50001 | LLM 或模板生成失败 |
| 50002 | RAG-SERVER 调用失败 |
| 50003 | MCP wrapper 调用失败 |
| 50004 | RAG ingestion proxy 任务失败 |
| 50005 | 安全校验失败 |

#### 5.6.2 RAG-SERVER Adapter 契约

`backend/app/schemas/rag_server.py`：

```python
from typing import Literal
from pydantic import BaseModel, Field

RagResultStatus = Literal["success", "empty", "low_confidence"]


class RagSource(BaseModel):
    title: str
    page: int | None = None
    section_title: str | None = None
    chunk_id: str | None = None
    document_id: str | int | None = None
    uri: str | None = None


class RagSearchHit(BaseModel):
    content: str
    score: float | None = None
    source: RagSource


class RagSearchResult(BaseModel):
    query: str
    status: RagResultStatus = "success"
    hits: list[RagSearchHit] = Field(default_factory=list)
    answer_text: str | None = None
    citations: list[str] = Field(default_factory=list)
    low_confidence: bool = False
    raw_stdout: str | None = None
    raw: dict | None = None


class RagServerError(BaseModel):
    error_code: str
    message: str
```

`backend/app/integrations/rag_server/base.py`：

```python
from abc import ABC, abstractmethod


class RagServerClientError(Exception):
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        super().__init__(f"{error_code}: {message}")


class RagServerClient(ABC):
    @abstractmethod
    async def query(self, query: str, top_k: int = 5, collection: str | None = None) -> RagSearchResult:
        ...

    @abstractmethod
    async def get_document_summary(self, doc_id: str, collection: str | None = None) -> str:
        ...

    @abstractmethod
    async def list_collections(self, include_stats: bool = True) -> list[str]:
        ...
```

错误处理规则：

- `query()` 正常返回 `RagSearchResult`。
- 空结果返回 `RagSearchResult(status="empty", hits=[], citations=[])`，不抛异常。
- 低置信返回 `RagSearchResult(status="low_confidence", low_confidence=True)`，不抛异常。
- 配置缺失、RAG-SERVER 不可用、超时、返回无法解析等失败统一抛 `RagServerClientError(error_code, message)`。
- `ToolCaller` 捕获 `RagServerClientError` 后写入 `ToolError` 和 `tool_call_log`，最终回答不得生成 citation。
- 超时必须映射为 `RAG_SERVER_TIMEOUT`，`tool_call_log.status` 必须为 `"timeout"`。
- `tool_call_log.status` 只允许：`"success"`、`"failed"`、`"timeout"`、`"skipped"`。

错误码：

| error_code | 含义 |
|---|---|
| `RAG_SERVER_NOT_CONFIGURED` | 未配置 RAG-SERVER 路径或模式。 |
| `RAG_SERVER_UNAVAILABLE` | RAG-SERVER 进程无法启动或 CLI 不可用。 |
| `RAG_SERVER_TIMEOUT` | 查询或 ingestion 超时。 |
| `RAG_SERVER_EMPTY_RESULT` | 返回为空。 |
| `RAG_SERVER_LOW_CONFIDENCE` | 结果低置信。 |
| `RAG_SERVER_BAD_RESPONSE` | 返回内容无法映射为标准结构。 |

CLI / MCP stdio 边界：

- V1 查询只走 `FakeRagServerClient` 或 `RagServerMcpClient`。
- `RagServerCliGateway` 只负责 ingestion，不负责生产查询结果。
- 如果后续临时保留 CLI query 调试，只能把 stdout 保存为 `raw_stdout` 或 `answer_text`，不得从自由文本中伪造 hits、score、citations。
- `RagServerMcpClient` 启动子进程时必须设置 `cwd=repo_path`。
- MCP 命令固定为 `python -m src.mcp_server.server`，不得使用 `mcp-server` console script。
- stderr 可以记录到日志；stdout 只能由 MCP/JSON-RPC 通道消费，不得打印业务日志。
- 查询超时或关闭 client 时必须终止子进程，避免泄漏后台进程。

#### 5.6.3 当前项目 MCP wrapper 契约

`livestock_rag_search` 输入：

```json
{
  "query": "犊牛腹泻的常见原因和处理建议",
  "domain": "disease",
  "species": "cattle",
  "top_k": 4,
  "collection": "default"
}
```

输出：

```json
{
  "results": [
    {
      "content": "...",
      "score": 0.86,
      "document_title": "犊牛腹泻防治技术手册",
      "page": 12,
      "section_title": "常见病因",
      "chunk_id": "doc_001_chunk_012"
    }
  ],
  "citations": [
    "《犊牛腹泻防治技术手册》P12，常见病因"
  ],
  "status": "success"
}
```

实现要求：

- 内部调用 `RagServerClient.query()`。
- 如果真实 RAG-SERVER MCP 工具返回的是 `TextContent`，必须通过 `RagServerMapper` 解析或保留为 `answer_text`，不能让 Agent 解析原始 JSON-RPC。
- 低置信或空结果返回 `RAG_SERVER_LOW_CONFIDENCE` 或 `RAG_SERVER_EMPTY_RESULT`。

`get_source_detail`：

- 优先调用 `RagServerClient.get_document_summary(doc_id)`。
- 如果只有 `chunk_id` 没有 `doc_id`，允许返回当前 query hit 中已有 source 信息，但必须标注 `detail_level: "citation_only"`。

`disease_risk_evaluator`：

- 当前项目规则工具，不调用 RAG-SERVER。

`body_measurement_analyzer`：

- 当前项目规则工具，不调用 RAG-SERVER。

MCP Resource / Prompt 边界：

- V1 不实现 MCP Resource 和 MCP Prompt。
- `backend/app/mcp_server/` 只保留 `tools.py`。
- 疾病问诊模板、体尺报告模板由 `TemplateLLM` 或普通 Python 模板持有，不作为 MCP Prompt 暴露。
- 如 V1.1 需要 Resource/Prompt，必须先补充 `MCP_SPEC.md` 和契约测试。

#### 5.6.4 AgentState 契约

```python
from typing import Any, Literal
from pydantic import BaseModel, Field

IntentType = Literal["general_qa", "disease_consultation", "measurement_analysis", "out_of_scope"]
RiskLevel = Literal["low", "medium", "high", "emergency"]


class RetrievedContext(BaseModel):
    content: str
    title: str
    score: float | None = None
    chunk_id: str | None = None
    document_id: str | int | None = None
    page: int | None = None
    section_title: str | None = None


class ToolError(BaseModel):
    tool_name: str
    error_code: str
    message: str


class AgentState(BaseModel):
    session_id: str
    user_query: str
    normalized_query: str | None = None
    intent: IntentType | None = None
    intent_confidence: float | None = None
    risk_level: RiskLevel | None = None
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[ToolError] = Field(default_factory=list)
    draft_answer: str | None = None
    final_answer: str | None = None
    need_follow_up: bool = False
    follow_up_questions: list[str] = Field(default_factory=list)
```

#### 5.6.5 SQLite 最小表结构

当前项目 SQLite 只保存应用层数据：

```sql
CREATE TABLE IF NOT EXISTS animal_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id TEXT UNIQUE NOT NULL,
    species TEXT,
    breed TEXT,
    gender TEXT,
    birth_date TEXT,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS body_measurement_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id TEXT NOT NULL,
    measure_date TEXT NOT NULL,
    body_height_cm REAL,
    body_length_cm REAL,
    chest_girth_cm REAL,
    chest_depth_cm REAL,
    chest_width_cm REAL,
    weight_kg REAL,
    source TEXT,
    confidence REAL,
    algorithm_version TEXT,
    measurement_batch_id TEXT,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(animal_id) REFERENCES animal_profile(animal_id)
);

CREATE TABLE IF NOT EXISTS rag_ingestion_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    file_path TEXT NOT NULL,
    collection TEXT,
    status TEXT DEFAULT 'pending',
    exit_code INTEGER,
    stdout_text TEXT,
    stderr_text TEXT,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS qa_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    user_query TEXT NOT NULL,
    intent TEXT,
    rag_mode TEXT,
    tools_used_json TEXT,
    retrieved_contexts_json TEXT,
    citations_json TEXT,
    final_answer TEXT,
    risk_level TEXT,
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tool_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    tool_name TEXT NOT NULL,
    input_json TEXT,
    output_json TEXT,
    status TEXT,
    error_code TEXT,
    error_message TEXT,
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

禁止创建当前项目自有 `document_chunk`、`embedding`、`vector_index` 等 RAG 存储表。

#### 5.6.6 API 契约

`POST /api/chat`

请求：

```json
{
  "session_id": "s_001",
  "user_id": "u_001",
  "query": "我家一头犊牛腹泻两天，精神差，怎么办？",
  "animal_id": null,
  "stream": false
}
```

响应 `data`：

```json
{
  "answer": "...",
  "intent": "disease_consultation",
  "risk_level": "high",
  "sources": [
    {
      "title": "犊牛腹泻防治技术手册",
      "page": 12,
      "section_title": "常见病因",
      "chunk_id": "doc_001_chunk_012"
    }
  ],
  "citations": [
    "《犊牛腹泻防治技术手册》P12，常见病因"
  ],
  "tools_used": ["livestock_rag_search", "disease_risk_evaluator"],
  "need_follow_up": false,
  "follow_up_questions": []
}
```

`POST /api/documents/upload`

V1 测试可以用 JSON 传本地夹具路径；真实 API 可用 multipart 文件上传。二者最终都必须创建 `rag_ingestion_task(status="pending")`。

JSON 测试请求：

```json
{
  "file_path": "tests/fixtures/docs/calf_diarrhea.md",
  "collection": "livestock",
  "domain": "disease",
  "species": "cattle"
}
```

响应 `data`：

```json
{
  "task_id": "task_001",
  "file_path": "data/uploads/calf_diarrhea.md",
  "collection": "livestock",
  "status": "pending"
}
```

`POST /api/tasks/{task_id}/index`

请求体可为空。V1 同步执行一次 RAG-SERVER CLI ingestion 代理调用，并返回最终状态。

响应 `data`：

```json
{
  "task_id": "task_001",
  "status": "success",
  "exit_code": 0,
  "stdout_text": "...",
  "stderr_text": "",
  "error_message": null
}
```

`GET /api/tasks/{task_id}`

响应 `data`：

```json
{
  "task_id": "task_001",
  "file_path": "data/uploads/calf_diarrhea.md",
  "collection": "livestock",
  "status": "success",
  "exit_code": 0,
  "error_message": null
}
```

`POST /api/measurement/analyze`

请求：

```json
{
  "animal_id": "yak_032",
  "age_month": 18,
  "current": {
    "body_height_cm": 114.2,
    "body_length_cm": 132.7,
    "chest_girth_cm": 158.4,
    "chest_depth_cm": 55.6,
    "chest_width_cm": 39.8,
    "weight_kg": 246.5
  },
  "confidence": 0.82,
  "use_demo_history": false
}
```

响应 `data`：

```json
{
  "animal_id": "yak_032",
  "summary": "...",
  "abnormal_items": ["chest_girth_cm"],
  "evidence": ["胸围从 157.0 cm 增至 158.4 cm，增长 1.4 cm"],
  "report": "...",
  "used_demo_history": false
}
```

API 错误映射：

| 场景 | code | message |
|---|---:|---|
| 请求字段缺失或非法 | 40001 | `invalid request` |
| `task_id` 不存在 | 40004 | `task not found` |
| RAG-SERVER 不可用或超时 | 50002 | `rag server unavailable` 或 `rag server timeout` |
| MCP wrapper 调用失败 | 50003 | `tool call failed` |
| ingestion 代理失败 | 50004 | `rag ingestion failed` |
| Final Safety Guard 不通过 | 50005 | `safety check failed` |

---

## 6. 项目排期

排期按 A 到 I 共 9 个阶段推进。每个子任务目标是约 1 小时可验收；若实际实现明显超过 1 小时，必须继续拆分。

### 阶段 A：项目骨架与契约护栏

目的：建立可运行、可测试、不会重写 RAG-SERVER 的最小工程骨架。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| A0 | 初始化本地虚拟环境规范 | `.gitignore`、`pyproject.toml`、可选 `requirements-dev.txt` | 无 | 根目录存在 `.venv` 使用说明，`.venv/` 已忽略，最小 dev 依赖可安装 | `python -m venv .venv` 后运行 `python -m pip install -e ".[dev]"` |
| A1 | 初始化 Python 包和测试目录 | `pyproject.toml`、`backend/app/__init__.py`、`tests/`、`scripts/` | 无 | `pytest` 能发现测试目录 | `pytest --collect-only` |
| A2 | 增加配置加载 | `config/settings.yaml`、`config/settings.test.yaml`、`backend/app/core/config.py`、`tests/unit/test_config.py` | `Settings`、`load_settings` | 测试配置默认 `rag_server.query_mode=fake` | `pytest tests/unit/test_config.py` |
| A3 | 增加统一响应与错误码 | `backend/app/core/response.py`、`backend/app/core/errors.py`、`tests/unit/test_response.py` | `ApiResponse`、`ErrorCode`、`AppError` | 成功/失败响应字段统一 | `pytest tests/unit/test_response.py` |
| A4 | 增加契约文档初稿 | `docs/API_SPEC.md`、`docs/MCP_SPEC.md`、`docs/RAG_SERVER_INTEGRATION.md`、`docs/SAFETY_SPEC.md`、`docs/HARNESS.md` | 无 | 明确“不重写 RAG-SERVER”和 adapter 契约 | 人工检查 |
| A5 | 增加一键检查脚本 | `scripts/check_all.py` | `main` | 能运行默认本地测试，不触发真实 RAG-SERVER | `python scripts/check_all.py --unit-only` |

### 阶段 B：Schema、SQLite 与应用层数据

目的：只建立当前项目需要的应用层数据，不保存 RAG chunk 或向量。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| B1 | 定义 Agent 和 RAG adapter schema | `backend/app/schemas/agent.py`、`backend/app/schemas/rag_server.py`、`tests/unit/test_schemas.py` | `AgentState`、`RagSearchResult`、`RagSearchHit` | schema 字段与 5.6 一致 | `pytest tests/unit/test_schemas.py` |
| B2 | 定义体尺和 API schema | `backend/app/schemas/api.py`、`backend/app/schemas/measurement.py`、`tests/unit/test_schemas.py` | `ChatRequest`、`MeasurementInput` | 请求字段校验正确 | `pytest tests/unit/test_schemas.py -k measurement` |
| B3 | 初始化 SQLite 应用表 | `backend/app/db/connection.py`、`backend/app/db/migrations.py`、`tests/integration/test_sqlite_schema.py` | `get_connection`、`init_db` | 创建 5.6.5 表；不创建 RAG chunk 表 | `pytest tests/integration/test_sqlite_schema.py` |
| B4 | 实现体尺 repository | `backend/app/db/repositories.py`、`tests/integration/test_measurement_repository.py` | `AnimalRepository`、`MeasurementRepository` | 能按 `animal_id` 查询历史记录 | `pytest tests/integration/test_measurement_repository.py` |
| B5 | 实现任务和日志 repository | `backend/app/db/repositories.py`、`tests/integration/test_task_and_log_repository.py` | `RagIngestionTaskRepository`、`ToolCallLogRepository`、`QaLogRepository` | 任务和日志可写可查 | `pytest tests/integration/test_task_and_log_repository.py` |

### 阶段 C：RAG-SERVER Adapter

目的：以 fake 优先方式建立 RAG-SERVER 接入边界。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| C1 | 定义 client 抽象 | `backend/app/integrations/rag_server/base.py`、`tests/integration/test_rag_server_client_contract.py` | `RagServerClient` | query、summary、collections 方法固定 | `pytest tests/integration/test_rag_server_client_contract.py -k interface` |
| C2 | 实现 fake client | `backend/app/integrations/rag_server/fake_client.py`、`tests/fixtures/rag_server/*.json`、`tests/unit/test_fake_rag_server_client.py` | `FakeRagServerClient` | 能返回成功、空结果、低置信、失败夹具 | `pytest tests/unit/test_fake_rag_server_client.py` |
| C3 | 实现结果 mapper | `backend/app/integrations/rag_server/mapper.py`、`tests/unit/test_rag_server_mapper.py` | `RagServerMapper.to_search_result` | 能把 fake/文本结果映射为 `RagSearchResult` | `pytest tests/unit/test_rag_server_mapper.py` |
| C4 | 实现 client factory | `backend/app/integrations/rag_server/__init__.py`、`tests/unit/test_config.py` | `create_rag_server_client` | `query_mode=fake` 默认返回 fake client | `pytest tests/unit/test_config.py -k rag_server` |
| C5 | 实现 RAG-SERVER 路径解析 | `backend/app/integrations/rag_server/health.py`、`tests/unit/test_config.py` | `resolve_rag_server_path` | `RAG_SERVER_PATH` 优先，相对路径相对项目根目录 | `pytest tests/unit/test_config.py -k rag_server_path` |
| C6 | 实现 CLI ingestion gateway | `backend/app/integrations/rag_server/cli_gateway.py`、`tests/integration/test_rag_server_cli_gateway.py` | `RagServerCliGateway.ingest` | 只代理 `scripts/ingest.py`；未配置路径时返回明确错误 | `pytest tests/integration/test_rag_server_cli_gateway.py -k ingest` |
| C7 | 实现 MCP stdio client 配置与进程生命周期 | `backend/app/integrations/rag_server/mcp_stdio_client.py`、`tests/integration/test_rag_server_mcp_client.py` | `RagServerMcpClient.start`、`close` | `cwd=repo_path`；超时/关闭会终止子进程；未设置路径跳过真实测试 | `pytest tests/integration/test_rag_server_mcp_client.py -k lifecycle` |
| C8 | 实现 MCP stdio query/list/summary 调用 | `backend/app/integrations/rag_server/mcp_stdio_client.py`、`tests/integration/test_rag_server_mcp_client.py` | `query`、`list_collections`、`get_document_summary` | 调用 `query_knowledge_hub`、`list_collections`、`get_document_summary` 并标准化结果 | `pytest tests/integration/test_rag_server_mcp_client.py -k tools` |

### 阶段 D：MCP wrapper 与答案生成

目的：把 RAG-SERVER 能力包装成畜牧应用工具，并保持失败降级。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| D1 | 定义 MCP wrapper schema | `backend/app/schemas/mcp.py`、`backend/app/mcp_server/tools.py`、`tests/integration/test_mcp_tools.py` | `ToolResult`、`ToolError`、`TOOL_SCHEMAS` | 4 个工具 schema 固定 | `pytest tests/integration/test_mcp_tools.py -k schema` |
| D2 | 实现 `livestock_rag_search` wrapper | `backend/app/mcp_server/tools.py`、`tests/integration/test_mcp_tools.py` | `livestock_rag_search` | 内部调用 `RagServerClient.query`，返回 citations | `pytest tests/integration/test_mcp_tools.py -k rag_search` |
| D3 | 实现 `get_source_detail` wrapper | `backend/app/mcp_server/tools.py`、`tests/integration/test_mcp_tools.py` | `get_source_detail` | 调用 summary 或返回 citation-only 详情 | `pytest tests/integration/test_mcp_tools.py -k source_detail` |
| D4 | 实现工具超时和日志 | `backend/app/agent/tool_caller.py`、`tests/integration/test_tool_timeout.py` | `ToolCaller.call_with_timeout` | 超时记录错误，不伪造 RAG 结果 | `pytest tests/integration/test_tool_timeout.py` |
| D5 | 实现模板模型 | `backend/app/model/base.py`、`backend/app/model/template_client.py`、`tests/unit/test_template_client.py` | `BaseLLMClient`、`TemplateLLM` | 不调用外部模型，输出可预测 | `pytest tests/unit/test_template_client.py` |
| D6 | 实现应用层答案拼装 | `backend/app/model/answer_generator.py`、`tests/unit/test_answer_generator.py` | `AnswerGenerator.compose_with_citations` | citations 只来自 `RagSearchResult`，不重新推断来源 | `pytest tests/unit/test_answer_generator.py` |

### 阶段 E：疾病风险、体尺分析与安全规则

目的：实现当前项目独有的畜牧领域规则能力。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| E1 | 实现疾病风险规则加载 | `backend/app/rules/disease_risk.yaml`、`backend/app/rules/disease_risk.py`、`tests/unit/test_disease_risk.py` | `DiseaseRiskEvaluator.evaluate` | emergency > high > medium；缺槽返回 missing_info | `pytest tests/unit/test_disease_risk.py` |
| E2 | 封装疾病风险工具 | `backend/app/mcp_server/tools.py`、`tests/integration/test_mcp_tools.py` | `disease_risk_evaluator` | 不调用 RAG-SERVER，不调用 LLM | `pytest tests/integration/test_mcp_tools.py -k disease` |
| E3 | 实现体尺分析器 | `backend/app/services/measurement_service.py`、`backend/app/rules/measurement_rules.yaml`、`tests/unit/test_measurement_analyzer.py` | `BodyMeasurementAnalyzer.analyze` | 异常有证据，无历史不判断趋势 | `pytest tests/unit/test_measurement_analyzer.py` |
| E4 | 封装体尺分析工具 | `backend/app/mcp_server/tools.py`、`tests/integration/test_mcp_tools.py` | `body_measurement_analyzer` | 输出 summary、abnormal_items、evidence、recommendation | `pytest tests/integration/test_mcp_tools.py -k measurement` |
| E5 | 实现 Safety Guard | `backend/app/agent/safety.py`、`backend/app/rules/safety_rules.yaml`、`tests/unit/test_safety.py` | `SafetyGuard`、`FinalSafetyGuard` | 剂量、确定诊断、处方、伪造工具结果被拦截 | `pytest tests/unit/test_safety.py` |

### 阶段 F：Agent Workflow

目的：完成应用层状态机编排。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| F1 | 实现意图路由 | `backend/app/agent/router.py`、`tests/unit/test_agent_router.py` | `IntentRouter.route` | 识别 general_qa、disease、measurement、out_of_scope | `pytest tests/unit/test_agent_router.py` |
| F2 | 实现槽位抽取和追问策略 | `backend/app/agent/extractor.py`、`tests/unit/test_slot_extractor.py` | `SlotExtractor.extract`、`build_follow_up_questions` | 疾病缺槽最多追问 3 个问题 | `pytest tests/unit/test_slot_extractor.py` |
| F3 | 实现 Verifier-lite | `backend/app/agent/verifier.py`、`tests/unit/test_verifier.py` | `VerifierLite.check` | 发现无引用专业结论、剂量、体尺无证据异常 | `pytest tests/unit/test_verifier.py` |
| F4 | 实现普通 QA workflow | `backend/app/agent/workflow.py`、`tests/integration/test_agent_workflow.py` | `run_general_qa` | 调用 fake RAG、生成引用并过安全 | `pytest tests/integration/test_agent_workflow.py -k general` |
| F5 | 实现疾病 workflow 的追问分支 | `backend/app/agent/workflow.py`、`tests/e2e/test_disease_consultation_flow.py` | `run_disease_consultation` | 缺少关键信息时最多追问 3 个问题，不调用 RAG | `pytest tests/e2e/test_disease_consultation_flow.py -k follow_up` |
| F6 | 实现疾病 workflow 的风险与 RAG 分支 | `backend/app/agent/workflow.py`、`tests/e2e/test_disease_consultation_flow.py` | `run_disease_consultation` | 信息充分时调用风险工具和 fake RAG | `pytest tests/e2e/test_disease_consultation_flow.py -k risk_rag` |
| F7 | 实现疾病 workflow 的最终安全分支 | `backend/app/agent/workflow.py`、`tests/e2e/test_disease_consultation_flow.py` | `run_disease_consultation` | Final Safety Guard 拦截剂量和确定诊断 | `pytest tests/e2e/test_disease_consultation_flow.py -k final_safety` |
| F8 | 实现体尺 workflow | `backend/app/agent/workflow.py`、`tests/e2e/test_measurement_report_flow.py` | `run_measurement_analysis` | 当前值、历史、异常、建议结构完整 | `pytest tests/e2e/test_measurement_report_flow.py` |

### 阶段 G：API 与本地脚本

目的：提供本地可调用入口。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| G1 | 实现 `/api/chat` | `backend/app/api/chat.py`、`backend/app/services/chat_service.py`、`tests/integration/test_api_contract.py` | `chat`、`ChatService.ask` | 统一响应，返回 intent、answer、sources、tools_used | `pytest tests/integration/test_api_contract.py -k chat` |
| G2 | 实现文档上传代理接口 | `backend/app/api/documents.py`、`backend/app/services/document_service.py`、`tests/integration/test_api_contract.py` | `upload_document` | 保存上传文件并创建 ingestion task | `pytest tests/integration/test_api_contract.py -k upload` |
| G3 | 实现 RAG-SERVER ingestion task 接口 | `backend/app/api/tasks.py`、`backend/app/services/task_service.py`、`tests/integration/test_api_contract.py` | `index_document_via_rag_server`、`get_task` | `POST /api/tasks/{task_id}/index` 同步执行并返回最终状态 | `pytest tests/integration/test_api_contract.py -k task` |
| G4 | 实现体尺分析接口 | `backend/app/api/measurement.py`、`backend/app/services/measurement_service.py`、`tests/integration/test_api_contract.py` | `analyze_measurement` | 演示历史标注正确，报告结构完整 | `pytest tests/integration/test_api_contract.py -k measurement` |
| G5 | 增加本地查询脚本 | `scripts/query.py`、`tests/integration/test_cli_scripts.py` | `query.main` | 使用 fake 或真实 RAG adapter 查询并输出引用 | `pytest tests/integration/test_cli_scripts.py -k query` |
| G6 | 增加 RAG-SERVER ingest 代理脚本 | `scripts/ingest_via_rag_server.py`、`tests/integration/test_cli_scripts.py` | `ingest_via_rag_server.main` | 只代理到 RAG-SERVER CLI，不解析文档 | `pytest tests/integration/test_cli_scripts.py -k ingest` |

### 阶段 H：E2E 与真实 RAG-SERVER 可选验证

目的：保证 fake 闭环稳定，并提供真实接入验证入口。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| H1 | 跑通文档问答 E2E fake | `tests/e2e/test_document_qa_flow.py` | 无 | fake RAG 下问答有引用 | `pytest tests/e2e/test_document_qa_flow.py` |
| H2 | 跑通疾病问诊 E2E fake | `tests/e2e/test_disease_consultation_flow.py` | 无 | 缺槽追问、高风险提示、安全拒答都通过 | `pytest tests/e2e/test_disease_consultation_flow.py` |
| H3 | 跑通体尺报告 E2E | `tests/e2e/test_measurement_report_flow.py` | 无 | 无历史/有历史/demo 历史三类通过 | `pytest tests/e2e/test_measurement_report_flow.py` |
| H4 | 增加真实 RAG-SERVER MCP smoke test | `tests/integration/test_rag_server_mcp_client.py` | 无 | 设置 `RAG_SERVER_PATH` 时可列工具或查询；未设置跳过 | `pytest -m rag_server` |
| H5 | 增加真实 RAG-SERVER CLI ingestion smoke test | `tests/integration/test_rag_server_cli_gateway.py` | 无 | `scripts/ingest.py --dry-run` 可执行；未设置跳过 | `pytest -m rag_server` |

### 阶段 I：评测、文档与交付检查

目的：形成可量化质量报告和最终交付材料。

| ID | 约 1 小时增量 | 修改文件列表 | 实现的类/函数 | 验收标准 | 测试方法 |
|---|---|---|---|---|---|
| I1 | 定义黄金评测 schema | `backend/app/evaluation/golden_runner.py`、`tests/unit/test_golden_set_schema.py` | `GoldenCase` | 单条样本字段校验明确 | `pytest tests/unit/test_golden_set_schema.py` |
| I2 | 建立普通问答和饲养管理评测样本 | `tests/fixtures/golden_set.json`、`tests/unit/test_golden_set_schema.py` | 无 | 覆盖 20 条知识类样本 | `pytest tests/unit/test_golden_set_schema.py -k knowledge_cases` |
| I3 | 建立疾病和高风险评测样本 | `tests/fixtures/golden_set.json`、`tests/unit/test_golden_set_schema.py` | 无 | 覆盖 25 条疾病/安全样本 | `pytest tests/unit/test_golden_set_schema.py -k disease_cases` |
| I4 | 建立体尺和无答案评测样本 | `tests/fixtures/golden_set.json`、`tests/unit/test_golden_set_schema.py` | 无 | 覆盖 15 条体尺/无答案样本，总数 60 | `pytest tests/unit/test_golden_set_schema.py -k distribution` |
| I5 | 实现指标计算 | `backend/app/evaluation/metrics.py`、`tests/unit/test_eval_metrics.py` | `compute_metrics` | 能计算意图、RAG 调用、引用、安全、追问等指标 | `pytest tests/unit/test_eval_metrics.py` |
| I6 | 实现评测 runner JSON 输出 | `backend/app/evaluation/golden_runner.py`、`scripts/run_eval.py`、`tests/integration/test_eval_runner.py` | `GoldenSetRunner.run` | 输出 `reports/eval_result.json` | `python scripts/run_eval.py --json` |
| I7 | 实现评测 CSV 和 summary 输出 | `backend/app/evaluation/golden_runner.py`、`scripts/run_eval.py`、`tests/integration/test_eval_runner.py` | `run_eval.main` | 输出 CSV 和 summary markdown | `python scripts/run_eval.py` |
| I8 | 校准规范文档 | `docs/API_SPEC.md`、`docs/MCP_SPEC.md`、`docs/RAG_SERVER_INTEGRATION.md`、`docs/SAFETY_SPEC.md`、`docs/EVAL_SPEC.md`、`docs/HARNESS.md` | 无 | 文档与实现契约一致 | `pytest tests/integration/test_api_contract.py tests/integration/test_mcp_tools.py` |
| I9 | 最终全量检查 | `scripts/check_all.py`、`reports/eval_summary.md` | `check_all.main` | 默认测试、E2E、评测全通过；默认不运行 `rag_server` marker | `python scripts/check_all.py` |

### 6.1 进度跟踪表

| 阶段 | 目标 | 子任务 | 状态 | 当前产物 | 验收命令 |
|---|---|---|---|---|---|
| A | 骨架与契约护栏 | A0-A5 | DONE | `.venv` 规范、配置、响应、契约文档、检查脚本 | `pytest --collect-only` |
| B | Schema 与 SQLite | B1-B5 | DONE | 应用层 schema、SQLite 表、repository | `pytest tests/integration/test_sqlite_schema.py` |
| C | RAG-SERVER Adapter | C1-C8 | DONE | fake/MCP client、CLI ingestion gateway、mapper、factory | `pytest tests/integration/test_rag_server_client_contract.py` |
| D | MCP wrapper 与答案拼装 | D1-D6 | DONE | 畜牧工具 wrapper、超时、应用层引用拼装 | `pytest tests/integration/test_mcp_tools.py` |
| E | 规则与安全 | E1-E5 | DONE | 疾病风险、体尺分析、Safety Guard | `pytest tests/unit/test_safety.py` |
| F | Agent Workflow | F1-F8 | DONE | router、extractor、verifier、三条 workflow | `pytest tests/integration/test_agent_workflow.py` |
| G | API 与脚本 | G1-G6 | DONE | API、query 脚本、ingest 代理脚本 | `pytest tests/integration/test_api_contract.py` |
| H | E2E 与真实接入验证 | H1-H5 | DONE | fake E2E、真实 RAG-SERVER smoke tests | `pytest tests/e2e` |
| I | 评测与交付 | I1-I9 | DONE | golden set、评测 runner、报告输出、交付文档 | `python scripts/check_all.py` |

### 6.2 每次开发提交前检查清单

- 是否误写了 parser、splitter、embedding、vector store、retriever 等 RAG-SERVER 已有能力。
- 是否已激活当前项目根目录 `.venv`，并使用 `.venv` 中的 Python 运行测试和脚本。
- `.venv/` 是否已加入 `.gitignore`，且没有被提交。
- 是否所有 RAG 调用都经过 `RagServerClient`。
- 默认测试是否仍然使用 fake RAG client。
- 是否新增或更新了对应测试。
- 是否修改 API / MCP / RAG adapter / Safety 契约；如修改，是否同步文档和契约测试。
- 是否可能输出药物剂量、确定性诊断或无依据异常结论。
- 是否在 RAG-SERVER 失败时伪造了检索结果或引用。
- 是否复制了 RAG-SERVER 配置中的真实密钥。
- `scripts/check_all.py` 默认是否等价于 `pytest -m "not rag_server"`，真实 RAG-SERVER smoke test 是否只能显式运行。
