# DEV_SPEC_v4_1：真实畜牧知识库质量闭环与 V3 主路径决策

> 本文档基于当前仓库实况扫描和 code reviewer subagent 反馈制定。它不是 V3/V4.0 的重复开发计划，而是从 V4.0-E 之后继续推进的下一阶段开发规范。

## 0. 当前基线

### 0.1 仓库实况

- 当前项目是 `Agentic RAG` 应用层项目，不是 `RAG-SERVER` 本体。
- 当前最新提交已超过用户早前提到的 `922f6f8`，扫描时最新提交为：
  - `f787ca8 资料：新增真实畜牧资料来源目录`
  - `32b317f V4.0-E：稳定真实RAG端到端链路并通过回归验证`
  - `922f6f8 V3.7-H4：固化真实 RAG 回归报告并完成 V3 阶段`
- 工作区没有已跟踪代码改动；存在未跟踪设计文档文件，应避免误提交无关文档。
- 现有 `DEV_SPEC_v4.md` 是 V4.0 真实 RAG 稳定化记录，本文件用于 V4.1 下一阶段。

### 0.2 已完成能力

- V1/V2：FastAPI、静态前端、SQLite、RAG fake/smoke/real 模式、RAG schema、trace、eval、文档/任务接口已经存在。
- V3：feature flags、SafetyPrecheck、ModelRouter shadow、低风险结构化任务接管、Verifier 增强、LoRA 数据治理 dry-run、Memory MVP、V3 eval/debug summary 已完成。
- V4.0：真实 RAG-SERVER MCP stdio 调用、preflight、timeout retry、source_uri/citation 映射、真实 eval 报告已完成。
- 当前 `/api/chat` 主路径仍通过 `ChatService -> run_general_qa/run_disease_consultation` 调 V2 workflow；`run_*_graph` 主要用于 V3 eval 和测试，不应误写成已经全面接入生产主路径。

### 0.3 已知质量问题

- 真实 RAG 链路已经能跑通，但当前 RAG-SERVER 真实知识库样本偏弱，主要依赖 `simple.pdf` 一类样本文档。
- 真实 eval 最近可跑通到 `55/60`，失败集中在 `no_answer` 场景：低相关样本文档被召回，导致系统未能保守拒答。
- `LocalModelClient.provider="mock"` 是结构化 mock，不是真实本地大模型推理。
- LoRA 当前是数据治理和导出 dry-run，不包含真实训练或推理启用。

## 1. 项目概述

### 1.1 设计理念

V4.1 的核心理念是：先把真实知识、真实评测和保守拒答闭环做扎实，再扩大模型能力。当前项目已经具备 agent、RAG adapter、trace 和 eval 的工程骨架，下一阶段最缺的是高质量畜牧知识源、可复现实测集、低置信检索处理和 API 主路径决策。

### 1.2 项目定位

本项目定位为本地优先、轻量级、零新增外部服务依赖的畜牧业 Agentic RAG 应用层：

- 以 FastAPI 提供业务 API 和前端 demo。
- 以 sibling `RAG-SERVER` 作为已有真实知识库服务，不在本项目内重新开发 RAG 内核。
- 以 SQLite、JSON/YAML、pytest 和本地脚本完成开发、评测和回归。
- 对兽医诊断、处方、用药剂量、停药期等高风险问题保持安全拒答和转人工边界。

## 2. 核心特点

| 特点 | 说明 |
|---|---|
| 真实 RAG 优先 | V4.1 不用 fake eval 证明真实质量，真实模式必须经过 RAG-SERVER preflight。 |
| 知识源可治理 | 每个入库候选资料必须有 `source_id`、`source_uri`、机构、语言、许可/版权备注和用途标记。 |
| no-answer 可评估 | 独立维护 no-answer golden cases，防止弱知识库或低相关召回污染答案。 |
| 配置驱动 | fake/smoke/real、V3 graph、ModelRouter、Memory、LoRA 均通过配置或环境变量显式启用。 |
| 安全边界前置 | 高风险问题优先通过 SafetyPrecheck/Final Safety Guard 处理，不依赖 RAG 结果兜底。 |
| 小步可验收 | 每个约 1 小时增量必须有文件清单、类/函数、验收标准、测试命令和简体中文 commit。 |

## 3. 技术选型

| 类别 | 选型 | 约束 |
|---|---|---|
| 语言 | Python 3.11+ | 后续开发和测试统一使用项目根目录 `.venv`。 |
| Web | FastAPI | 保持现有 API contract，不做框架替换。 |
| 数据 | SQLite | 本地优先，不新增 PostgreSQL、Redis、云服务。 |
| 配置 | YAML + Pydantic | `config/settings.yaml` 为默认配置，敏感信息不写入文档和提交。 |
| RAG | sibling `RAG-SERVER` MCP stdio | 不重写 RAG-SERVER；真实接入需要显式 `RAG_SERVER_PATH`。 |
| 测试 | pytest | 单元、集成、E2E、真实 RAG optional 分层执行。 |
| 文档 | Markdown | 资料源 manifest 用 YAML/Markdown，可版本化但不保存版权受限全文。 |

## 4. 开发与提交流程硬约束

### 4.1 虚拟环境

所有开发、测试、脚本运行都必须使用项目根目录的 `.venv`：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -m "not rag_server" -q
```

禁止在 DEV_SPEC 执行过程中直接使用系统 Python 或其它项目虚拟环境运行本项目测试。真实 RAG-SERVER 可以通过 `RAG_SERVER_PYTHON` 指向 RAG-SERVER 自己的 Python，但 Agentic RAG 侧仍使用本项目 `.venv`。

### 4.2 commit 规则

每完成一个小阶段任务并通过对应验收命令后，必须提交一次 commit：

```powershell
git add <本小阶段修改文件>
git commit -m "V4.1-A1：固化真实 RAG 质量基线"
```

提交消息必须使用简体中文，格式建议为：

```text
V4.1-<阶段编号>：<本次可验收增量>
```

不得把 `.venv/`、`.tmp_tests/`、`data/`、`reports/`、API key、RAG-SERVER 配置明文、版权受限全文提交进仓库。

### 4.3 真实 RAG 接入边界

- 不允许为了通过真实 RAG 测试而静默切回 fake。
- 需要真实 RAG 时，先读取 `AGENTS.md` 中的 RAG-SERVER 说明。
- 默认 RAG-SERVER 路径为 `C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER`。
- 如缺少 `RAG_SERVER_PATH`、`RAG_SERVER_PYTHON`、collection、API key 或入库资料文件，必须向用户确认，不能用 fake 替代。
- 本项目可以调用 RAG-SERVER CLI/MCP 做预检、查询、入库 dry-run 或用户批准后的真实入库；不得修改 RAG-SERVER 源码和配置，除非用户单独授权。

## 5. 测试方案

### 5.1 TDD 原则

每个功能改动遵循：

1. 先写失败测试或扩展 golden case。
2. 运行目标测试确认失败原因准确。
3. 写最小实现。
4. 运行目标测试、阶段验收测试和必要回归。
5. 简体中文 commit。

### 5.2 分层测试

| 层级 | 目标 | 典型命令 |
|---|---|---|
| 单元测试 | manifest schema、mapper、metrics、no-answer policy、config 解析 | `.venv\Scripts\python.exe -m pytest tests/unit -q` |
| 集成测试 | RAG adapter、preflight、eval runner、trace API、ChatService 路径切换 | `.venv\Scripts\python.exe -m pytest tests/integration -q` |
| E2E 测试 | `/api/chat`、前端 contract、V3 disabled 回归、memory flow | `.venv\Scripts\python.exe -m pytest tests/e2e -q` |
| 真实 RAG smoke | 真实 RAG-SERVER MCP 可用性和 collection 可发现 | `.venv\Scripts\python.exe -m pytest -m rag_server -q` |
| 真实 eval | 真实知识库质量、no-answer、安全和引用覆盖 | `.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real_v4_1` |

### 5.3 agent 性能评估

V4.1 的 agent 评估不新增“更多 agent”，而是评估现有 agent 是否稳定：

- 路由准确率：`intent_accuracy >= 0.95`。
- RAG 调用正确性：该查时查、不该查时不查。
- 引用覆盖：answerable real cases 的 `rag_citation_coverage` 和 `source_uri_coverage` 目标为 `1.0`。
- no-answer 准确率：真实 no-answer cases 目标不低于 `0.95`。
- 安全通过率：高风险拒答 cases 目标为 `1.0`。
- trace 完整性：真实 RAG case 应可追踪 request、RAG mode、collection、mapping warnings、error code。

## 6. 系统架构与模块设计

### 6.1 整体架构图

```text
+------------------+      +------------------+      +----------------------+
| Browser / Client | ---> | FastAPI /api/*   | ---> | ChatService / Router |
+------------------+      +------------------+      +----------+-----------+
                                                              |
                            v3.enabled=false                  | v3.enabled=true
                                                              |
                         +----------------+          +---------v----------+
                         | V2 Workflow    |          | V3 Agent Graph     |
                         | run_general_*  |          | Supervisor/RAG/... |
                         +--------+-------+          +---------+----------+
                                  |                            |
                                  +-------------+--------------+
                                                |
                                      +---------v----------+
                                      | RAG-SERVER Adapter |
                                      | mapper/preflight   |
                                      +---------+----------+
                                                |
                                      MCP stdio | real mode only
                                                |
                                      +---------v----------+
                                      | sibling RAG-SERVER |
                                      | existing project   |
                                      +--------------------+

+----------------------+      +------------------+      +------------------+
| source_manifest.yaml | ---> | RAG corpus plan  | ---> | real eval runner |
+----------------------+      +------------------+      +------------------+
                                                            |
                                                            v
                                                   reports / metrics
```

### 6.2 目录结构树

V4.1 规划后的关键目录如下：

```text
Agentic RAG/
├── DEV_SPEC_v4_1.md
├── README.md
├── config/
│   └── settings.yaml
├── backend/
│   └── app/
│       ├── api/
│       │   ├── chat.py
│       │   └── traces.py
│       ├── agent/
│       │   ├── graph.py
│       │   ├── verifier.py
│       │   └── workflow.py
│       ├── core/
│       │   └── config.py
│       ├── evaluation/
│       │   ├── golden_runner.py
│       │   ├── metrics.py
│       │   ├── real_rag_preflight.py
│       │   ├── real_rag_runner.py
│       │   └── source_manifest.py        # V4.1 新增
│       ├── integrations/
│       │   └── rag_server/
│       │       ├── diagnostics.py
│       │       ├── mapper.py
│       │       └── mcp_stdio_client.py
│       └── services/
│           ├── chat_service.py
│           └── trace_service.py
├── docs/
│   ├── REAL_LIVESTOCK_SOURCE_CATALOG.md
│   ├── V4_1_BASELINE.md                 # V4.1 新增
│   └── rag_corpus/                       # V4.1 新增
│       ├── source_manifest.yaml
│       ├── corpus_batch_01.md
│       └── ingestion_plan.md
├── scripts/
│   ├── check_v2.py
│   ├── check_v3.py
│   ├── check_v4_1.py                     # V4.1 新增
│   └── run_eval.py
└── tests/
    ├── fixtures/
    │   ├── golden_set.json
    │   └── real_golden_v4_1/             # V4.1 新增
    │       ├── answerable.json
    │       ├── no_answer.json
    │       └── safety.json
    ├── integration/
    └── unit/
```

### 6.3 模块职责说明

| 模块 | 职责 | V4.1 改动原则 |
|---|---|---|
| `backend/app/core/config.py` | 配置模型和默认值 | 仅新增真实 RAG 质量阈值等必要字段，保持默认不破坏现有 fake/V2。 |
| `backend/app/evaluation/source_manifest.py` | 资料源 manifest 解析和校验 | 新增，负责验证 source_id、source_uri、许可、用途和入库状态。 |
| `backend/app/evaluation/golden_runner.py` | golden set 执行和检查 | 扩展真实评测 metadata，不破坏现有 fake golden set。 |
| `backend/app/evaluation/metrics.py` | 指标聚合 | 增加 no-answer、低置信、source quality 相关统计。 |
| `backend/app/evaluation/real_rag_runner.py` | 真实 RAG eval | 支持 V4.1 分组 golden set 和输出更清楚的失败分类。 |
| `backend/app/integrations/rag_server/mapper.py` | RAG-SERVER 返回映射 | 增强低置信/空结果判定，不伪造不完整 citation。 |
| `backend/app/model/answer_generator.py` | 基于 RAG result 生成回答 | 在低置信和 no-answer 时输出保守拒答。 |
| `backend/app/agent/verifier.py` | 最终答案轻量校验 | 对需要引用但证据不足的答案标记失败。 |
| `backend/app/services/chat_service.py` | `/api/chat` 业务入口 | 只在 feature flag 明确开启时切到 V3 graph。 |
| `scripts/check_v4_1.py` | 阶段验收入口 | 聚合 manifest、评测集、真实 RAG optional 和回归检查。 |

### 6.4 数据流说明

1. 资料目录：`docs/REAL_LIVESTOCK_SOURCE_CATALOG.md` 提供候选来源。
2. 治理清单：人工筛选后写入 `docs/rag_corpus/source_manifest.yaml`。
3. 入库计划：`docs/rag_corpus/ingestion_plan.md` 记录哪些来源可入库、哪些只用于 eval/redteam。
4. RAG-SERVER 入库：只对用户批准、低版权风险、已准备本地文件或摘要的来源执行。
5. 真实预检：`RealRagPreflightRunner` 确认 RAG-SERVER、collection、tools 和查询 smoke。
6. 业务查询：`ChatService` 根据配置走 V2 workflow 或 V3 graph，再通过 adapter 调真实 RAG。
7. 映射与回答：`RagServerMapper` 生成标准 schema，`AnswerGenerator` 基于证据生成回答或拒答。
8. 评测报告：`run_eval.py --mode real` 输出 JSON/CSV/Markdown，失败由 `failure_analysis.md` 分类。

### 6.5 配置驱动设计示例

`config/settings.yaml` 示例：

```yaml
rag_server:
  query_mode: real
  repo_path: "C:\\Users\\DELL\\PycharmProjects\\PythonProject\\RAG-SERVER"
  python_executable: null
  collection: livestock_v4_1
  timeout_seconds: 30
  strict_real_mode: true
  min_mapped_score: 0.35
  min_citation_count_for_answer: 1
  low_confidence_no_answer: true

v3:
  enabled: false

model_router:
  enabled: false
  shadow_mode: true
  allow_low_risk_takeover: false

local_model:
  enabled: false
  provider: mock

lora:
  dataset_enabled: false
  inference_enabled: false
```

`source_manifest.yaml` 示例：

```yaml
version: 1
collection: livestock_v4_1
sources:
  - source_id: umn_preweaning_calf_health
    title: Pre-weaning calf health
    source_uri: https://extension.umn.edu/dairy-youngstock/pre-weaning-calf-health
    language: EN
    organization: University of Minnesota Extension
    source_type: university_extension
    topics: [calf_health, diarrhea, respiratory]
    usage: [knowledge_base, eval]
    ingestion_status: approved_summary_only
    license_note: "教育网页；只入库人工摘要、关键事实和链接，不复制全文。"
    reviewed_by: human
```

## 7. 项目排期

> 每个子任务设计为约 1 小时一个可验收增量。执行时必须按子任务提交 commit。

### 进度跟踪表

| 阶段 | 目的 | 状态 |
|---|---|---|
| V4.1-A | 固化当前基线和检查入口 | 已完成 |
| V4.1-B | 建立资料源治理和 manifest schema | 已完成 |
| V4.1-C | 准备第一批真实语料入库计划 | 已完成 |
| V4.1-D | 增强真实 RAG preflight 与 corpus 对齐检查 | 已完成 |
| V4.1-E | 构建真实评测集 v4.1 | 已完成 |
| V4.1-F | no-answer 与低置信检索硬化 | 已完成 |
| V4.1-G | 决策并实现 V3 graph 是否接入 `/api/chat` 主路径 | 已完成 |
| V4.1-H | trace、debug 和报告工程化 | 已完成 |
| V4.1-I | 发布文档、回归和阶段收口 | 已完成 |

### V4.1-A：固化当前基线和检查入口

**目的：** 防止后续 agent 把已完成的 V3/V4.0 能力重复开发，并明确当前真实问题是知识库质量和 no-answer。

#### A1. 编写 V4.1 baseline 文档

- 修改文件：
  - 新增 `docs/V4_1_BASELINE.md`
  - 修改 `README.md`
- 实现的类/函数：无
- 验收标准：
  - 文档明确最新阶段为 V4.0-E 之后。
  - 文档明确 V3 默认关闭、local model 是 mock、LoRA 是 dry-run。
  - 文档明确真实 RAG 当前质量问题是 no-answer/弱知识库，不是链路不可用。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  git diff --check
  ```
- commit：
  ```powershell
  git commit -m "V4.1-A1：固化下一阶段开发基线"
  ```

#### A2. 新增 V4.1 阶段检查脚本

- 修改文件：
  - 新增 `scripts/check_v4_1.py`
  - 新增 `tests/integration/test_check_v4_1.py`
- 实现的类/函数：
  - `main(argv: list[str] | None = None) -> int`
  - `check_required_files(root: Path) -> list[str]`
  - `check_real_golden_sets(root: Path) -> list[str]`
  - `check_source_manifest(root: Path) -> list[str]`
- 验收标准：
  - `--stage baseline` 能检查 README、DEV_SPEC_v4_1、V4_1_BASELINE 是否存在。
  - `--stage corpus` 能检查 manifest 和真实 golden set 是否存在。
  - `--stage full` 能串联 baseline、corpus、现有 V2/V3 检查。
  - 脚本只读，不启动真实 RAG，不写 reports。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_v4_1.py -q
  .venv\Scripts\python.exe scripts\check_v4_1.py --stage baseline
  ```
- commit：
  ```powershell
  git commit -m "V4.1-A2：新增 V4.1 阶段检查脚本"
  ```

### V4.1-B：建立资料源治理和 manifest schema

**目的：** 把 `docs/REAL_LIVESTOCK_SOURCE_CATALOG.md` 转成可校验、可追踪、可入库决策的数据结构。

#### B1. 新增 source manifest 解析器

- 修改文件：
  - 新增 `backend/app/evaluation/source_manifest.py`
  - 新增 `tests/unit/test_source_manifest.py`
- 实现的类/函数：
  - `SourceManifest`
  - `SourceManifestEntry`
  - `load_source_manifest(path: str | Path) -> SourceManifest`
  - `validate_source_manifest(manifest: SourceManifest) -> list[str]`
- 验收标准：
  - 必填字段缺失时返回明确错误。
  - `source_id` 必须唯一。
  - `source_uri` 必须是 http/https。
  - `usage` 只允许 `knowledge_base`、`eval`、`redteam`、`reference`。
  - `ingestion_status` 只允许 `approved_summary_only`、`approved_full_text`、`eval_only`、`reference_only`、`blocked`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_source_manifest.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-B1：新增资料源清单校验模型"
  ```

#### B2. 创建第一批 source manifest

- 修改文件：
  - 新增 `docs/rag_corpus/source_manifest.yaml`
  - 新增 `docs/rag_corpus/corpus_batch_01.md`
- 实现的类/函数：无
- 验收标准：
  - 从真实资料目录中选择 8-12 个低版权风险来源。
  - 每条来源包含 `source_id`、`title`、`source_uri`、`language`、`organization`、`topics`、`usage`、`ingestion_status`、`license_note`。
  - 不复制版权受限全文；只记录摘要、关键事实、引用锚点和链接。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_1.py --stage corpus
  .venv\Scripts\python.exe -m pytest tests/unit/test_source_manifest.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-B2：建立第一批真实资料源清单"
  ```

### V4.1-C：准备第一批真实语料入库计划

**目的：** 在不修改 RAG-SERVER 源码的前提下，形成可人工复核、可执行的入库计划。

#### C1. 编写入库计划文档

- 修改文件：
  - 新增 `docs/rag_corpus/ingestion_plan.md`
  - 修改 `docs/rag_corpus/corpus_batch_01.md`
- 实现的类/函数：无
- 验收标准：
  - 明确哪些来源只入库人工摘要，哪些来源可入库全文。
  - 明确本地文件路径占位规则，例如 `C:\tmp\livestock_corpus\batch_01\...`。
  - 明确 RAG-SERVER 执行命令只作为用户确认后的操作。
- 测试方法：
  ```powershell
  git diff --check docs/rag_corpus
  .venv\Scripts\python.exe scripts\check_v4_1.py --stage corpus
  ```
- commit：
  ```powershell
  git commit -m "V4.1-C1：编写第一批真实语料入库计划"
  ```

#### C2. 增加入库前 dry-run 检查

- 修改文件：
  - 新增 `scripts/check_rag_corpus.py`
  - 新增 `tests/integration/test_check_rag_corpus.py`
- 实现的类/函数：
  - `collect_manifest_sources(manifest_path: Path) -> list[SourceManifestEntry]`
  - `validate_local_corpus_files(entries: list[SourceManifestEntry], corpus_root: Path) -> list[str]`
  - `build_rag_server_ingest_commands(entries: list[SourceManifestEntry], collection: str) -> list[str]`
- 验收标准：
  - 默认只输出 dry-run 结果，不写 RAG-SERVER。
  - 缺少本地文件时返回可读错误。
  - 不打印 API key，不读取 RAG-SERVER `config/settings.yaml` 的敏感字段。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_rag_corpus.py -q
  .venv\Scripts\python.exe scripts\check_rag_corpus.py --manifest docs\rag_corpus\source_manifest.yaml --dry-run
  ```
- commit：
  ```powershell
  git commit -m "V4.1-C2：新增真实语料入库前检查"
  ```

### V4.1-D：增强真实 RAG preflight 与 corpus 对齐检查

**目的：** 真实 RAG eval 运行前，不仅确认 MCP 可用，还确认目标 collection 和预期语料批次一致。

#### D1. preflight 输出 corpus 信息

- 修改文件：
  - 修改 `backend/app/evaluation/real_rag_preflight.py`
  - 修改 `backend/app/evaluation/real_rag_runner.py`
  - 新增/修改 `tests/integration/test_real_rag_preflight.py`
- 实现的类/函数：
  - `RealRagPreflightReport.expected_collection`
  - `RealRagPreflightReport.manifest_source_count`
  - `RealRagPreflightRunner.run()`
- 验收标准：
  - 配置 collection 与 manifest collection 不一致时输出 warning。
  - preflight report 写入 `target_collection`、`manifest_collection`、`manifest_source_count`。
  - 真实 RAG 不可用时仍按 optional 语义写 skipped report，不 fake fallback。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_real_rag_preflight.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-D1：增强真实 RAG 预检语料对齐信息"
  ```

#### D2. 真实 RAG smoke 固化到 V4.1 检查

- 修改文件：
  - 修改 `scripts/check_v4_1.py`
  - 修改 `tests/integration/test_check_v4_1.py`
- 实现的类/函数：
  - `run_real_rag_smoke(optional: bool) -> int`
  - `check_real_rag_report(output_dir: Path) -> list[str]`
- 验收标准：
  - 默认 `--stage full` 不强制启动真实 RAG。
  - 显式 `--real-rag` 才运行 `pytest -m rag_server` 和 real eval optional。
  - 真实 RAG skipped 时退出码为 0 但报告必须说明原因。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_v4_1.py -q
  .venv\Scripts\python.exe scripts\check_v4_1.py --stage full
  ```
- commit：
  ```powershell
  git commit -m "V4.1-D2：将真实 RAG smoke 纳入可选检查"
  ```

### V4.1-E：构建真实评测集 v4.1

**目的：** 把 fake regression 和 real quality evaluation 拆开，建立 answerable、no-answer、安全红队三类真实评测集。

#### E1. 增加真实 golden set schema 校验

- 修改文件：
  - 修改 `backend/app/evaluation/golden_runner.py`
  - 新增 `tests/unit/test_real_golden_set_schema.py`
- 实现的类/函数：
  - `GoldenCase.source_ids: list[str]`
  - `GoldenCase.language: str | None`
  - `GoldenCase.expected_answer_type: Literal["answerable", "no_answer", "safety_refusal"]`
- 验收标准：
  - 旧 `tests/fixtures/golden_set.json` 兼容不破。
  - 新真实 golden case 可记录 `source_ids` 和语言。
  - no-answer case 不要求 citation。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_real_golden_set_schema.py tests/integration/test_eval_runner.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-E1：扩展真实评测集结构"
  ```

#### E2. 编写第一批真实评测样本

- 修改文件：
  - 新增 `tests/fixtures/real_golden_v4_1/answerable.json`
  - 新增 `tests/fixtures/real_golden_v4_1/no_answer.json`
  - 新增 `tests/fixtures/real_golden_v4_1/safety.json`
- 实现的类/函数：无
- 验收标准：
  - 第一批不少于 30 条：answerable 12 条、no-answer 10 条、安全红队 8 条。
  - 每条 answerable 样本至少关联一个 `source_id`。
  - no-answer 样本必须覆盖超出知识库、跨物种、缺少上下文、非畜牧问题。
  - 安全样本覆盖药物剂量、处方、停药期、确定性诊断和替代兽医。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_1.py --stage corpus
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --golden-set tests\fixtures\real_golden_v4_1\no_answer.json --output-dir reports\real_v4_1_no_answer
  ```
- commit：
  ```powershell
  git commit -m "V4.1-E2：新增第一批真实 RAG 评测样本"
  ```

### V4.1-F：no-answer 与低置信检索硬化

**目的：** 解决真实 eval 中 no-answer 被弱相关文档污染的问题。

#### F1. 增加 RAG 低置信策略配置

- 修改文件：
  - 修改 `backend/app/core/config.py`
  - 修改 `config/settings.yaml`
  - 新增/修改 `tests/unit/test_config.py`
- 实现的类/函数：
  - `RagServerSettings.min_mapped_score`
  - `RagServerSettings.min_citation_count_for_answer`
  - `RagServerSettings.low_confidence_no_answer`
- 验收标准：
  - 默认值不改变现有 fake 测试。
  - 配置解析支持缺省字段。
  - 文档明确阈值仅用于 Agentic RAG 应用层，不修改 RAG-SERVER 检索算法。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_config.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-F1：新增 RAG 低置信策略配置"
  ```

#### F2. mapper 和 answer generator 支持 low_confidence

- 修改文件：
  - 修改 `backend/app/integrations/rag_server/mapper.py`
  - 修改 `backend/app/model/answer_generator.py`
  - 修改 `backend/app/schemas/rag_server.py`
  - 新增/修改 `tests/unit/test_rag_server_mapper.py`
- 实现的类/函数：
  - `RagSearchResult.has_usable_hits`
  - `RagServerMapper.to_search_result(...)`
  - `AnswerGenerator.compose_with_citations(...)`
- 验收标准：
  - 当 top hit 低于阈值或 citation 不足时，`status="low_confidence"`。
  - `low_confidence` 输出标准 no-answer 文案。
  - 不为缺少 doc_id/chunk_id 的 hit 伪造 citation。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_rag_server_mapper.py tests/unit/test_eval_metrics.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-F2：硬化低置信 RAG 拒答逻辑"
  ```

#### F3. real eval 增加 no-answer 失败分类

- 修改文件：
  - 修改 `backend/app/evaluation/metrics.py`
  - 修改 `backend/app/evaluation/failure_analysis.py`
  - 新增/修改 `tests/unit/test_eval_metrics.py`
- 实现的类/函数：
  - `compute_metrics(...)`
  - `_rag_observability_summary(...)`
  - `build_failure_summary(...)`
- 验收标准：
  - failure categories 区分 `NO_ANSWER_FALSE_POSITIVE`、`LOW_CONFIDENCE_ACCEPTED`、`MISSING_CITATION`。
  - real eval summary 能看出 no-answer 是否改善。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_eval_metrics.py -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --golden-set tests\fixtures\real_golden_v4_1\no_answer.json --output-dir reports\real_v4_1_no_answer
  ```
- commit：
  ```powershell
  git commit -m "V4.1-F3：细化真实评测失败分类"
  ```

### V4.1-G：决策并实现 V3 graph 是否接入 `/api/chat` 主路径

**目的：** 明确 V3 graph 的生产边界。若启用，必须通过 feature flag 且保持 V3 off 时 V2 等价。

#### G1. 先写 API 主路径决策文档

- 修改文件：
  - 新增 `docs/V3_API_PATH_DECISION.md`
- 实现的类/函数：无
- 验收标准：
  - 明确默认仍为 V2 workflow。
  - 明确 `v3.enabled=true` 时才允许 `/api/chat` 使用 graph。
  - 明确 local model 和 LoRA 仍不作为真实生产推理能力。
- 测试方法：
  ```powershell
  git diff --check docs/V3_API_PATH_DECISION.md
  ```
- commit：
  ```powershell
  git commit -m "V4.1-G1：明确 V3 主路径接入决策"
  ```

#### G2. `/api/chat` 支持按 flag 切换 V3 graph

- 修改文件：
  - 修改 `backend/app/services/chat_service.py`
  - 修改 `backend/app/api/chat.py`
  - 新增/修改 `tests/integration/test_api_contract.py`
  - 新增/修改 `tests/e2e/test_v3_disabled_regression.py`
- 实现的类/函数：
  - `ChatService.__init__(rag_client: RagServerClient, settings: Settings | None = None)`
  - `ChatService.ask(request: ChatRequest) -> AgentState | MultiAgentState`
  - `state_to_chat_data(...)`
- 验收标准：
  - `v3.enabled=false` 时现有 API 响应不破。
  - `v3.enabled=true` 时 general/disease 路径走 `run_general_qa_graph` 或 `run_disease_graph`。
  - response 包含可调试的 agent path、safety、verifier 信息。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/e2e/test_v3_disabled_regression.py tests/integration/test_api_contract.py tests/integration/test_agent_graph.py -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode v3 --output-dir reports\v3
  ```
- commit：
  ```powershell
  git commit -m "V4.1-G2：按配置切换 V3 API 主路径"
  ```

### V4.1-H：trace、debug 和报告工程化

**目的：** 让每次真实 RAG 和 V3 graph 请求都能被定位、复盘和比较。

#### H1. 贯通 request_id 到 agent/RAG trace

- 修改文件：
  - 修改 `backend/app/api/chat.py`
  - 修改 `backend/app/services/chat_service.py`
  - 修改 `backend/app/services/trace_service.py`
  - 新增/修改 `tests/integration/test_trace_api.py`
- 实现的类/函数：
  - `TraceService.log_agent_trace(...)`
  - `TraceService.log_rag_trace(...)`
  - `v3_debug_summary(...)`
- 验收标准：
  - `/api/chat` 返回的 `request_id` 可用于 `/api/traces/{request_id}` 查询。
  - trace 中能看到 RAG mode、collection、mapping warnings、agent path。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_trace_api.py tests/integration/test_rag_trace.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-H1：贯通请求级 trace 查询"
  ```

#### H2. real eval 报告增加 source quality 摘要

- 修改文件：
  - 修改 `backend/app/evaluation/real_rag_runner.py`
  - 修改 `backend/app/evaluation/metrics.py`
  - 新增/修改 `tests/integration/test_eval_runner.py`
- 实现的类/函数：
  - `RealRagEvalRunner._write_summary(...)`
  - `_rag_observability_summary(...)`
- 验收标准：
  - `eval_summary.md` 输出 collection、preflight status、source_uri coverage、mapping warnings、no-answer accuracy。
  - `failure_analysis.md` 能直接列出 no-answer 失败 case。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py tests/unit/test_eval_metrics.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.1-H2：补强真实评测来源质量摘要"
  ```

### V4.1-I：发布文档、回归和阶段收口

**目的：** 把 V4.1 从开发任务收束为可交付状态。

#### I1. 更新用户文档和运行手册

- 修改文件：
  - 修改 `README.md`
  - 修改 `docs/HARNESS.md`
  - 修改 `docs/EVAL_SPEC.md`
  - 修改 `docs/RAG_SERVER_INTEGRATION.md`
- 实现的类/函数：无
- 验收标准：
  - 文档明确 fake、smoke、real、v3、mock local model、LoRA dry-run 的边界。
  - 文档给出真实 RAG 环境变量和 `.venv` 命令。
  - 文档说明真实入库需要用户确认资料和 RAG-SERVER 配置。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  git diff --check README.md docs
  ```
- commit：
  ```powershell
  git commit -m "V4.1-I1：更新 V4.1 运行和评测文档"
  ```

#### I2. 全量回归和阶段报告

- 修改文件：
  - 修改 `DEV_SPEC_v4_1.md`
  - 新增 `docs/V4_1_COMPLETION_REPORT.md`
- 实现的类/函数：无
- 验收标准：
  - 默认非真实 RAG 测试通过。
  - V2/V3 检查通过。
  - 真实 RAG 可用时，real eval 可完成并输出失败归因；真实 RAG 不可用时，optional skipped 报告清楚说明原因。
  - 进度跟踪表更新为已完成。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest -m "not rag_server" -q
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  .venv\Scripts\python.exe scripts\check_v3.py --stage full
  .venv\Scripts\python.exe scripts\check_v4_1.py --stage full
  $env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
  .venv\Scripts\python.exe -m pytest -m rag_server -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real_v4_1
  ```
- commit：
  ```powershell
  git commit -m "V4.1-I2：完成 V4.1 阶段回归与报告"
  ```

## 8. 风险与处理策略

| 风险 | 处理策略 |
|---|---|
| RAG-SERVER 知识库资料不足 | 先做 source manifest 和第一批 corpus，不通过 fake 掩盖真实质量。 |
| 版权受限资料被误入库 | 只入库人工摘要、关键事实、链接和引用锚点；高风险来源仅用于 reference/redteam。 |
| 真实 RAG 环境不可用 | optional eval 写 skipped report；需要配置时询问用户，不自行替换为 fake。 |
| V3 graph 主路径引入回归 | 默认关闭；先写 V3 disabled regression，再做 flag 切换。 |
| 阈值调优过拟合 | no-answer、answerable、安全集分开统计；阈值必须配置化并记录报告。 |
| 运行产物污染仓库 | `.tmp_tests/`、`data/`、`reports/` 保持忽略；只提交文档、代码、测试和小型 fixture。 |

## 9. 阶段完成定义

V4.1 完成必须同时满足：

- `scripts/check_v4_1.py --stage full` 通过。
- 默认测试 `.venv\Scripts\python.exe -m pytest -m "not rag_server" -q` 通过。
- `scripts/check_v2.py --offline --frontend-contract --docs` 通过。
- `scripts/check_v3.py --stage full` 通过。
- 真实 RAG 可用时，`run_eval.py --mode real --optional` 生成完整报告，不出现 fake fallback。
- no-answer 真实评测有独立通过率和失败分类。
- README 和相关 docs 明确 V4.1 能力边界，不把 mock/dry-run 写成生产能力。
- 每个小阶段都有简体中文 commit。
