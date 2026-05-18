# DEV_SPEC_v4_2：V4 剩余阶段开发总规范

> 本文档承接 `DEV_SPEC_v4_1.md`，用于统一规划 V4 剩余阶段：V4.2、V4.3、V4.4、V4.5。默认前提是 V4.1 已完成：真实资料源清单、第一批 corpus plan、真实评测集、no-answer/低置信策略、V3 主路径决策和 V4.1 检查脚本均已落地。本文档不重复建设 V3/V4.1 骨架，而是把 V4 从“真实 RAG 质量闭环成立”推进到“真实知识库可扩展、检索质量可优化、产品工作台可用、长期记忆可控读取”。

## 0. 阶段定位

### 0.1 V4.2-V4.5 要解决的问题

V4.1 解决的是“真实 RAG 质量闭环能否成立”。V4.2 解决的是“真实知识库能否持续扩展，并且每次扩展都能被质量门禁约束”。

V4 剩余阶段的核心问题包括：

- 第一批真实资料不足以覆盖畜牧业主要问答场景。
- source manifest 需要从文档清单升级为可校验、可版本化、可追踪的知识库治理资产。
- RAG-SERVER 入库过程需要被 dry-run、批次记录、评测报告和回滚策略约束。
- 真实 eval 需要成为质量门禁，而不是开发者手动查看的参考报告。
- no-answer、citation、source_uri、source quality 等指标需要按 collection 版本持续比较。
- 检索质量问题需要从真实失败案例中定位，不能靠堆 prompt 或 fake fixture 掩盖。
- 前端 demo 需要升级为本地工作台，能展示知识库、评测、trace 和人工复核状态。
- 长期记忆需要从“写入 MVP”进入“可控读取、可解释、可删除”的闭环。

### 0.2 V4 剩余阶段不做什么

- 不开发新的 RAG-SERVER 内核。
- 不修改 RAG-SERVER 源码或配置，除非用户单独授权。
- 不把版权受限全文、API key、RAG-SERVER 私有配置提交到本仓库。
- 不把 mock local model 写成真实本地模型能力。
- 不进入 LoRA 真实训练和推理启用阶段。
- 不为了通过真实评测而回退 fake。
- V4.5 只做长期记忆读取闭环，不做真实本地模型接管；真实本地模型和 LoRA 留到 V5。

## 1. 项目概述

### 1.1 设计理念

V4.2-V4.5 采用“资料治理先于检索优化，检索质量先于模型升级，记忆读取先于模型接管”的原则。只有当知识源、入库批次、评测集、质量报告、调试界面和长期记忆读取都可追踪时，后续真实本地模型或 LoRA 才有可靠的评估基础。

### 1.2 项目定位

V4.2-V4.5 后，项目应具备一个可持续维护的本地畜牧智能助手工程流程：

- 资料源从 `docs/REAL_LIVESTOCK_SOURCE_CATALOG.md` 进入 versioned manifest。
- 每个入库批次有 batch id、来源、文件、摘要、collection、入库命令和评测结果。
- 每次真实 RAG 扩展都必须通过 preflight、smoke、real eval 和质量门禁。
- 评测报告能说明质量变化，而不仅是“通过/失败”。
- 用户能在本地工作台查看知识库状态、评测报告、trace、引用和安全拒答原因。
- 长期记忆能读取用户确认事实，并能解释来源、置信度和过期状态。

## 2. 核心特点

| 特点 | 说明 |
|---|---|
| 批次化知识库 | 每批 corpus 都有 manifest、ingestion plan、collection version 和验收报告。 |
| 质量门禁 | real eval 指标低于阈值时阻止阶段完成，不允许用 fake 替代。 |
| 来源可追踪 | answerable case 必须能追溯到 `source_id` 和 `source_uri`。 |
| no-answer 稳定 | 扩容知识库后仍要保持 no-answer 准确率，防止无关召回污染答案。 |
| 本地优先 | 所有检查、报告和数据治理在本地完成，不新增外部服务依赖。 |
| 可回滚 | 每个 collection/batch 都能定位到入库计划和评测结果，必要时可重建。 |

## 3. 技术选型

| 类别 | 选型 | V4 剩余阶段约束 |
|---|---|---|
| 语言 | Python 3.11+ | 继续使用项目根目录 `.venv`。 |
| 测试 | pytest | 真实 RAG 测试仍使用 `rag_server` marker。 |
| 数据治理 | YAML/JSON/Markdown | manifest 和 batch report 需要版本化。 |
| 本地数据库 | SQLite | 仅在确有必要时增加轻量元数据表。 |
| RAG | sibling RAG-SERVER MCP/CLI | 只调用，不重写。 |
| 报告 | Markdown + JSON + CSV | 适合 git diff、人工审阅和脚本检查。 |

## 4. 开发流程硬约束

### 4.1 虚拟环境

所有本项目命令必须使用：

```powershell
.venv\Scripts\python.exe
```

示例：

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server" -q
.venv\Scripts\python.exe scripts\check_v4_2.py --stage full
```

真实 RAG-SERVER 如需独立解释器，通过环境变量配置：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
$env:RAG_SERVER_PYTHON="C:\path\to\rag-server-python.exe"
```

### 4.2 commit 规则

每个约 1 小时增量完成并通过对应测试后，必须提交一次简体中文 commit：

```powershell
git add <本小阶段修改文件>
git commit -m "V4.2-A1：建立知识库批次模型"
```

禁止提交：

- `.venv/`
- `.tmp_tests/`
- `data/`
- `reports/`
- RAG-SERVER 真实 API key
- 版权受限全文
- RAG-SERVER 私有配置文件

### 4.3 真实 RAG 规则

- `--mode real` 必须保持真实 RAG 语义。
- 真实 RAG 不可用时可以 optional skipped，但报告必须说明原因。
- 缺少资料文件、collection、RAG-SERVER 配置或 API key 时，必须询问用户。
- 不允许自动下载、批量抓取或全文复制版权不明资料。

## 5. 测试方案

### 5.1 TDD 流程

1. 先写 manifest、batch、quality gate 或 eval 的失败测试。
2. 运行目标测试确认失败。
3. 实现最小功能。
4. 运行单元/集成/真实 RAG optional 检查。
5. 更新文档和进度表。
6. 简体中文 commit。

### 5.2 分层测试

| 层级 | 内容 | 命令 |
|---|---|---|
| 单元 | manifest schema、batch schema、quality gate、指标比较 | `.venv\Scripts\python.exe -m pytest tests/unit -q` |
| 集成 | `check_v4_2.py`、real eval report、source coverage report | `.venv\Scripts\python.exe -m pytest tests/integration -q` |
| E2E | API、前端、V3 disabled regression | `.venv\Scripts\python.exe -m pytest tests/e2e -q` |
| 非真实 RAG 回归 | 默认本地回归 | `.venv\Scripts\python.exe -m pytest -m "not rag_server" -q` |
| 真实 RAG smoke | RAG-SERVER MCP 可用性 | `.venv\Scripts\python.exe -m pytest -m rag_server -q` |
| 真实质量门禁 | batch collection 真实评测 | `.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_2` |

### 5.3 V4.2 质量门禁指标

| 指标 | 最低要求 | 说明 |
|---|---:|---|
| real eval pass rate | `>= 0.90` | 全量真实评测最低线。 |
| answerable citation coverage | `>= 0.95` | 可回答问题必须有来源。 |
| source_uri coverage | `>= 0.95` | 来源必须能追溯。 |
| no-answer accuracy | `>= 0.95` | 防止知识库扩容后误答。 |
| safety pass rate | `1.00` | 高风险问题必须拒答或转人工。 |
| mapping warning count | 不得新增未知类型 | 新 warning 必须分类说明。 |
| RAG error count | `0` | 真实链路不应有 timeout/schema/tool error。 |

## 6. 系统架构与模块设计

### 6.1 整体架构图

```text
 docs/REAL_LIVESTOCK_SOURCE_CATALOG.md
                 |
                 v
 +-------------------------------+
 | docs/rag_corpus/source_*.yaml |
 | source manifest versions      |
 +---------------+---------------+
                 |
                 v
 +-------------------------------+
 | docs/rag_corpus/batches/*.yaml|
 | batch id / files / collection |
 +---------------+---------------+
                 |
                 v
 +-------------------------------+       +----------------------+
 | scripts/check_rag_corpus.py   | ----> | RAG-SERVER CLI/MCP   |
 | dry-run / command generation  |       | existing project     |
 +---------------+---------------+       +----------+-----------+
                 |                                  |
                 v                                  v
 +-------------------------------+       +----------------------+
 | RealRagPreflightRunner        | ----> | target collection    |
 +---------------+---------------+       +----------------------+
                 |
                 v
 +-------------------------------+
 | run_eval.py --mode real       |
 | metrics / failure analysis    |
 +---------------+---------------+
                 |
                 v
 +-------------------------------+
 | QualityGate                   |
 | pass/fail + delta comparison  |
 +-------------------------------+
```

### 6.2 目录结构树

V4.2 规划后的关键结构：

```text
Agentic RAG/
├── DEV_SPEC_v4_2.md
├── backend/
│   └── app/
│       ├── evaluation/
│       │   ├── corpus_batch.py          # V4.2 新增
│       │   ├── quality_gate.py          # V4.2 新增
│       │   ├── source_manifest.py       # V4.1 延续增强
│       │   ├── metrics.py
│       │   └── real_rag_runner.py
│       └── integrations/
│           └── rag_server/
│               ├── diagnostics.py
│               └── mcp_stdio_client.py
├── docs/
│   └── rag_corpus/
│       ├── source_manifest.yaml
│       ├── manifests/
│       │   ├── livestock_v4_1.yaml
│       │   └── livestock_v4_2.yaml
│       ├── batches/
│       │   ├── batch_001.yaml
│       │   └── batch_002.yaml
│       ├── reports/
│       │   └── batch_002_quality.md
│       └── ingestion_plan.md
├── scripts/
│   ├── check_v4_1.py
│   ├── check_v4_2.py                  # V4.2 新增
│   ├── check_rag_corpus.py            # V4.1 延续增强
│   └── run_eval.py
└── tests/
    ├── fixtures/
    │   └── real_golden_v4_2/
    │       ├── all.json
    │       ├── answerable.json
    │       ├── no_answer.json
    │       ├── safety.json
    │       └── bilingual.json
    ├── integration/
    │   ├── test_check_v4_2.py
    │   └── test_quality_gate.py
    └── unit/
        ├── test_corpus_batch.py
        └── test_quality_gate.py
```

### 6.3 模块职责说明

| 模块 | 职责 |
|---|---|
| `backend/app/evaluation/source_manifest.py` | 校验资料源 manifest，保证来源可追踪。 |
| `backend/app/evaluation/corpus_batch.py` | 定义 corpus batch、入库文件、collection、状态和报告路径。 |
| `backend/app/evaluation/quality_gate.py` | 读取 eval report，按阈值判断 V4.2 是否通过。 |
| `backend/app/evaluation/metrics.py` | 继续扩展 source coverage、no-answer、safety、delta 指标。 |
| `backend/app/evaluation/real_rag_runner.py` | 输出可被 quality gate 读取的真实评测报告。 |
| `scripts/check_v4_2.py` | 阶段验收入口，聚合 manifest、batch、eval、gate 和回归。 |
| `scripts/check_rag_corpus.py` | 入库 dry-run 和 RAG-SERVER 命令生成。 |
| `docs/rag_corpus/batches/*.yaml` | 每批真实语料的可审计记录。 |

### 6.4 corpus batch 配置示例

```yaml
batch_id: batch_002
collection: livestock_v4_2
manifest: docs/rag_corpus/manifests/livestock_v4_2.yaml
created_at: "2026-05-18"
status: planned
sources:
  - source_id: umn_preweaning_calf_health
    ingestion_mode: summary_only
    local_file: C:\tmp\livestock_corpus\batch_002\umn_preweaning_calf_health.md
    expected_topics: [calf_health, diarrhea, respiratory]
  - source_id: usda_aphis_scours
    ingestion_mode: summary_only
    local_file: C:\tmp\livestock_corpus\batch_002\usda_aphis_scours.md
    expected_topics: [diarrhea, epidemiology]
quality_gate:
  min_pass_rate: 0.90
  min_no_answer_accuracy: 0.95
  min_source_uri_coverage: 0.95
  required_safety_pass_rate: 1.00
```

## 7. 项目排期

> 每个子任务约 1 小时一个可验收增量。执行时按子任务提交简体中文 commit。

### 进度跟踪表

| 阶段 | 目的 | 状态 |
|---|---|---|
| V4.2-A | 建立 corpus batch 数据模型 | 已完成 |
| V4.2-B | 建立 V4.2 manifest 和 batch 目录 | 已完成 |
| V4.2-C | 增强入库 dry-run 和命令生成 | 已完成 |
| V4.2-D | 建立真实评测集 V4.2 | 已完成 |
| V4.2-E | 增加质量门禁 QualityGate | 已完成 |
| V4.2-F | 固化真实 RAG batch 回归流程 | 已完成 |
| V4.2-G | 增加报告对比和质量趋势 | 已完成 |
| V4.2-H | 前端/调试页展示真实知识库状态 | 已完成 |
| V4.2-I | 文档、全量回归和阶段收口 | 未开始 |

### V4.2-A：建立 corpus batch 数据模型

**目的：** 让真实知识库扩展从“临时手工入库”变成“有批次记录的工程流程”。

#### A1. 新增 corpus batch schema

- 修改文件：
  - 新增 `backend/app/evaluation/corpus_batch.py`
  - 新增 `tests/unit/test_corpus_batch.py`
- 实现的类/函数：
  - `CorpusBatch`
  - `CorpusBatchSource`
  - `CorpusQualityGateConfig`
  - `load_corpus_batch(path: str | Path) -> CorpusBatch`
  - `validate_corpus_batch(batch: CorpusBatch) -> list[str]`
- 验收标准：
  - `batch_id`、`collection`、`manifest`、`sources` 必填。
  - `source_id` 在同一 batch 内唯一。
  - `ingestion_mode` 只允许 `summary_only`、`full_text`、`metadata_only`。
  - `local_file` 不存在时返回明确校验错误，但不自动创建文件。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_corpus_batch.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.2-A1：新增知识库批次数据模型"
  ```

#### A2. 将 batch 校验接入 V4.2 检查脚本

- 修改文件：
  - 新增 `scripts/check_v4_2.py`
  - 新增 `tests/integration/test_check_v4_2.py`
- 实现的类/函数：
  - `main(argv: list[str] | None = None) -> int`
  - `check_batch_files(root: Path) -> list[str]`
  - `check_manifest_alignment(root: Path) -> list[str]`
- 验收标准：
  - `--stage batch` 检查 batch 文件存在并可解析。
  - `--stage full` 默认不启动真实 RAG。
  - 错误输出包含具体文件路径和字段名。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_v4_2.py -q
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage batch
  ```
- commit：
  ```powershell
  git commit -m "V4.2-A2：新增 V4.2 批次检查入口"
  ```

### V4.2-B：建立 V4.2 manifest 和 batch 目录

**目的：** 在 V4.1 第一批资料基础上，规划第二批可入库资料和真实 collection 版本。

#### B1. 建立 manifest 版本目录

- 修改文件：
  - 新增 `docs/rag_corpus/manifests/livestock_v4_2.yaml`
  - 修改 `docs/rag_corpus/source_manifest.yaml`
  - 新增 `docs/rag_corpus/README.md`
- 实现的类/函数：无
- 验收标准：
  - `livestock_v4_2.yaml` 至少包含 15 个来源。
  - 每个来源都有 `source_id`、`source_uri`、`language`、`organization`、`usage`、`license_note`。
  - 来源分层清楚：knowledge_base、eval、redteam、reference。
  - 不复制版权受限全文。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage batch
  git diff --check docs/rag_corpus
  ```
- commit：
  ```powershell
  git commit -m "V4.2-B1：建立 V4.2 资料源清单版本"
  ```

#### B2. 建立第二批 corpus batch

- 修改文件：
  - 新增 `docs/rag_corpus/batches/batch_002.yaml`
  - 新增 `docs/rag_corpus/batches/README.md`
- 实现的类/函数：无
- 验收标准：
  - batch 指向 `collection: livestock_v4_2`。
  - batch 至少选择 8 个 knowledge_base 来源。
  - 每个 source 都标记 `ingestion_mode` 和 `local_file`。
  - 对缺少本地文件的条目，状态标为 `planned`，不得伪造已入库。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage batch
  ```
- commit：
  ```powershell
  git commit -m "V4.2-B2：建立第二批真实语料批次"
  ```

### V4.2-C：增强入库 dry-run 和命令生成

**目的：** 让用户在真实入库前能清楚看到会调用哪些 RAG-SERVER 命令、会入哪个 collection、缺少哪些文件。

#### C1. 扩展 `check_rag_corpus.py` 支持 batch

- 修改文件：
  - 修改 `scripts/check_rag_corpus.py`
  - 新增/修改 `tests/integration/test_check_rag_corpus.py`
- 实现的类/函数：
  - `load_batch_or_manifest(path: Path) -> CorpusBatch | SourceManifest`
  - `build_ingest_plan(batch: CorpusBatch) -> list[IngestCommand]`
  - `render_ingest_plan(commands: list[IngestCommand]) -> str`
- 验收标准：
  - 支持 `--batch docs\rag_corpus\batches\batch_002.yaml`。
  - 默认 dry-run 只输出命令，不执行。
  - 输出命令包含 collection、文件路径、source_id。
  - 不打印任何 API key。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_rag_corpus.py -q
  .venv\Scripts\python.exe scripts\check_rag_corpus.py --batch docs\rag_corpus\batches\batch_002.yaml --dry-run
  ```
- commit：
  ```powershell
  git commit -m "V4.2-C1：支持按批次生成 RAG 入库计划"
  ```

#### C2. 增加入库后批次报告模板

- 修改文件：
  - 新增 `docs/rag_corpus/reports/batch_002_quality.md`
  - 修改 `scripts/check_v4_2.py`
- 实现的类/函数：
  - `check_batch_report(batch_id: str, root: Path) -> list[str]`
- 验收标准：
  - 报告包含 batch id、collection、来源数量、入库状态、preflight、eval summary、失败分类。
  - 若真实入库尚未执行，报告状态明确为 `planned` 或 `not_ingested`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage batch
  git diff --check docs/rag_corpus/reports
  ```
- commit：
  ```powershell
  git commit -m "V4.2-C2：新增知识库批次质量报告模板"
  ```

### V4.2-D：建立真实评测集 V4.2

**目的：** 扩展真实评测集，使其能覆盖第二批知识源、双语检索和扩容后的 no-answer 稳定性。

#### D1. 新增 V4.2 真实评测 fixtures

- 修改文件：
  - 新增 `tests/fixtures/real_golden_v4_2/answerable.json`
  - 新增 `tests/fixtures/real_golden_v4_2/no_answer.json`
  - 新增 `tests/fixtures/real_golden_v4_2/safety.json`
  - 新增 `tests/fixtures/real_golden_v4_2/bilingual.json`
  - 新增 `tests/fixtures/real_golden_v4_2/all.json`
- 实现的类/函数：无
- 验收标准：
  - 总样本不少于 80 条。
  - answerable 不少于 35 条。
  - no-answer 不少于 20 条。
  - safety redteam 不少于 15 条。
  - bilingual 不少于 10 条。
  - answerable 样本必须绑定 `source_ids`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage eval
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_2
  ```
- commit：
  ```powershell
  git commit -m "V4.2-D1：新增 V4.2 真实评测集"
  ```

#### D2. 增加评测集与 manifest 对齐检查

- 修改文件：
  - 修改 `scripts/check_v4_2.py`
  - 新增/修改 `tests/integration/test_check_v4_2.py`
- 实现的类/函数：
  - `check_golden_source_ids(golden_path: Path, manifest_path: Path) -> list[str]`
  - `check_golden_distribution(golden_dir: Path) -> list[str]`
- 验收标准：
  - answerable case 的 `source_ids` 必须存在于 manifest。
  - no-answer case 不得绑定不存在的 source。
  - distribution 不达标时给出类别计数。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_v4_2.py -q
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage eval
  ```
- commit：
  ```powershell
  git commit -m "V4.2-D2：校验真实评测集与资料源对齐"
  ```

### V4.2-E：增加质量门禁 QualityGate

**目的：** 将真实 eval 报告转化为明确的通过/失败判定。

#### E1. 新增 quality gate 模块

- 修改文件：
  - 新增 `backend/app/evaluation/quality_gate.py`
  - 新增 `tests/unit/test_quality_gate.py`
- 实现的类/函数：
  - `QualityGateThresholds`
  - `QualityGateResult`
  - `load_eval_report(path: str | Path) -> dict`
  - `evaluate_quality_gate(report: dict, thresholds: QualityGateThresholds) -> QualityGateResult`
- 验收标准：
  - pass rate、no-answer、source_uri、safety 任一不达标则 failed。
  - 输出 failed reasons，包含实际值和阈值。
  - skipped real eval 不能被判定为 passed。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_quality_gate.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.2-E1：新增真实评测质量门禁"
  ```

#### E2. 将 quality gate 接入脚本

- 修改文件：
  - 修改 `scripts/check_v4_2.py`
  - 新增/修改 `tests/integration/test_quality_gate.py`
- 实现的类/函数：
  - `run_quality_gate(report_path: Path, batch_path: Path) -> int`
  - `render_quality_gate_summary(result: QualityGateResult) -> str`
- 验收标准：
  - `scripts\check_v4_2.py --stage gate --report reports\real_v4_2\eval_result.json` 可独立运行。
  - gate failed 时退出码非 0。
  - optional skipped 报告输出清楚原因，不误判通过。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_quality_gate.py -q
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage gate --report reports\real_v4_2\eval_result.json
  ```
- commit：
  ```powershell
  git commit -m "V4.2-E2：将质量门禁接入 V4.2 检查"
  ```

### V4.2-F：固化真实 RAG batch 回归流程

**目的：** 形成一条从 batch 到 real eval 到 gate 的标准命令链。

#### F1. 新增 batch eval runner 参数

- 修改文件：
  - 修改 `scripts/run_eval.py`
  - 修改 `backend/app/evaluation/real_rag_runner.py`
  - 新增/修改 `tests/integration/test_eval_runner.py`
- 实现的类/函数：
  - `--batch <path>`
  - `RealRagEvalRunner.batch`
  - `RealRagEvalRunner._write_summary(...)`
- 验收标准：
  - `--batch` 能读取 collection 和 quality gate 阈值。
  - report 中写入 batch id、collection、manifest path。
  - 不影响原有 `--mode fake/multi_agent/v3/real`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --batch docs\rag_corpus\batches\batch_002.yaml --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_2
  ```
- commit：
  ```powershell
  git commit -m "V4.2-F1：支持按知识库批次运行真实评测"
  ```

#### F2. 新增标准 batch 回归命令

- 修改文件：
  - 新增 `scripts/check_real_batch.ps1`
  - 新增/修改 `docs/HARNESS.md`
- 实现的类/函数：无
- 验收标准：
  - PowerShell 脚本只编排本项目命令，不写死 API key。
  - 脚本要求用户显式传入 batch 和 output-dir。
  - 缺少 RAG_SERVER_PATH 时输出说明并退出。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
  git diff --check scripts docs
  ```
- commit：
  ```powershell
  git commit -m "V4.2-F2：新增真实批次回归命令"
  ```

### V4.2-G：增加报告对比和质量趋势

**目的：** 让每次知识库扩容后的质量变化可见。

#### G1. 新增 eval report diff 工具

- 修改文件：
  - 新增 `backend/app/evaluation/report_diff.py`
  - 新增 `scripts/diff_eval_reports.py`
  - 新增 `tests/unit/test_report_diff.py`
- 实现的类/函数：
  - `EvalMetricDelta`
  - `compare_eval_reports(before: dict, after: dict) -> list[EvalMetricDelta]`
  - `render_metric_delta_markdown(deltas: list[EvalMetricDelta]) -> str`
- 验收标准：
  - 能比较 pass_rate、no_answer_accuracy、source_uri_coverage、safety_pass_rate。
  - 能列出新增失败类别和新增 mapping warning。
  - 不要求历史 reports 被提交到 git。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_report_diff.py -q
  .venv\Scripts\python.exe scripts\diff_eval_reports.py --before reports\real_v4_1\eval_result.json --after reports\real_v4_2\eval_result.json
  ```
- commit：
  ```powershell
  git commit -m "V4.2-G1：新增真实评测报告对比工具"
  ```

#### G2. 批次质量报告写入趋势摘要

- 修改文件：
  - 修改 `docs/rag_corpus/reports/batch_002_quality.md`
  - 修改 `scripts/check_v4_2.py`
- 实现的类/函数：
  - `check_quality_report_has_delta(report_path: Path) -> list[str]`
- 验收标准：
  - 报告包含与上一版本相比的关键指标变化。
  - 若没有上一版本报告，必须明确写 `baseline: none`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage report
  git diff --check docs/rag_corpus/reports
  ```
- commit：
  ```powershell
  git commit -m "V4.2-G2：记录知识库批次质量趋势"
  ```

### V4.2-H：前端/调试页展示真实知识库状态

**目的：** 让用户能从本地 demo 看见当前 RAG 模式、collection、batch 和质量状态。

#### H1. 增加 API 状态字段

- 修改文件：
  - 修改 `backend/app/api/traces.py`
  - 修改 `backend/app/services/chat_service.py`
  - 新增/修改 `tests/integration/test_trace_api.py`
- 实现的类/函数：
  - `build_rag_status_payload(settings: Settings) -> dict`
  - `v4_2_quality_summary(...)`
- 验收标准：
  - debug payload 包含 `rag_mode`、`collection`、`batch_id`、`quality_gate_status`。
  - 未配置真实 RAG 时不报错，显示 `not_configured`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_trace_api.py tests/integration/test_api_contract.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.2-H1：暴露真实知识库状态调试字段"
  ```

#### H2. 前端 Debug 面板展示 RAG 批次状态

- 修改文件：
  - 修改 `backend/app/static/frontend/app.js`
  - 修改 `backend/app/static/frontend/styles.css`
  - 新增/修改 `tests/integration/test_frontend_contract.py`
- 实现的类/函数：
  - `renderDebugPanel(...)`
  - `renderRagStatus(...)`
- 验收标准：
  - 前端显示当前 `rag_mode`、`collection`、source count、quality gate。
  - 不显示 API key、RAG-SERVER 私有路径中的敏感信息。
  - 小屏不发生文字重叠。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.2-H2：前端展示真实知识库批次状态"
  ```

### V4.2-I：文档、全量回归和阶段收口

**目的：** 将 V4.2 作为可交付阶段封版。

#### I1. 更新文档

- 修改文件：
  - 修改 `README.md`
  - 修改 `docs/RAG_SERVER_INTEGRATION.md`
  - 修改 `docs/EVAL_SPEC.md`
  - 修改 `docs/HARNESS.md`
  - 新增 `docs/V4_2_KNOWLEDGE_BASE_GUIDE.md`
- 实现的类/函数：无
- 验收标准：
  - 文档说明 source manifest、batch、quality gate 的关系。
  - 文档说明真实入库需要用户确认资料和 RAG-SERVER 配置。
  - 文档列出标准 V4.2 验收命令。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  git diff --check README.md docs
  ```
- commit：
  ```powershell
  git commit -m "V4.2-I1：更新知识库规模化开发文档"
  ```

#### I2. 全量回归和完成报告

- 修改文件：
  - 修改 `DEV_SPEC_v4_2.md`
  - 新增 `docs/V4_2_COMPLETION_REPORT.md`
- 实现的类/函数：无
- 验收标准：
  - 默认非真实 RAG 测试通过。
  - V2/V3/V4.1/V4.2 检查通过。
  - 真实 RAG 可用时，batch eval 和 quality gate 通过。
  - 真实 RAG 不可用时，optional skipped 报告原因清楚，不能作为完成真实质量门禁的证据。
  - 进度表更新为已完成。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest -m "not rag_server" -q
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  .venv\Scripts\python.exe scripts\check_v3.py --stage full
  .venv\Scripts\python.exe scripts\check_v4_1.py --stage full
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
  $env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
  .venv\Scripts\python.exe -m pytest -m rag_server -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --batch docs\rag_corpus\batches\batch_002.yaml --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_2
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage gate --report reports\real_v4_2\eval_result.json
  ```
- commit：
  ```powershell
  git commit -m "V4.2-I2：完成 V4.2 知识库质量门禁阶段"
  ```

## 8. 风险与处理策略

| 风险 | 策略 |
|---|---|
| 真实资料版权不清 | 只做摘要、元数据、链接和少量事实；高风险资料仅用于 reference/redteam。 |
| RAG-SERVER 入库失败 | 先 dry-run，再用户确认真实入库；失败报告保留原因，不 fake fallback。 |
| collection 版本混乱 | batch 必须指定 collection，preflight report 必须记录 target collection。 |
| 知识库扩容导致 no-answer 下降 | quality gate 强制 no-answer accuracy 阈值。 |
| eval 过拟合 | answerable、no-answer、safety、bilingual 分开统计，并做报告 diff。 |
| 前端暴露敏感信息 | Debug 面板只显示模式、collection、状态，不显示 API key 和私有配置。 |

## 9. V4.2 完成定义

V4.2 完成必须同时满足：

- `DEV_SPEC_v4_2.md` 中所有阶段状态更新。
- `docs/rag_corpus/manifests/livestock_v4_2.yaml` 和 `docs/rag_corpus/batches/batch_002.yaml` 存在并通过校验。
- `tests/fixtures/real_golden_v4_2/all.json` 存在，且样本分布满足要求。
- `scripts/check_v4_2.py --stage full` 通过。
- 默认非真实 RAG 回归通过。
- 真实 RAG 可用时，batch real eval 跑完并通过 quality gate。
- README、HARNESS、EVAL、RAG integration 文档更新。
- 每个小阶段都有简体中文 commit。

## 10. V4.3：检索质量优化

### 10.1 阶段目的

V4.3 的目标是在 V4.2 质量门禁基础上，针对真实失败案例优化检索质量。优化顺序必须是：先归因，再调整应用层查询/阈值/评测，再决定是否需要用户授权修改 RAG-SERVER 配置。默认仍不修改 RAG-SERVER 源码。

### 10.2 进度跟踪表

| 子阶段 | 目的 | 状态 |
|---|---|---|
| V4.3-A | 建立检索失败归因基线 | 未开始 |
| V4.3-B | 查询改写与双语归一化 | 未开始 |
| V4.3-C | citation/source ranking 质量策略 | 未开始 |
| V4.3-D | RAG-SERVER 配置建议报告 | 未开始 |
| V4.3-E | V4.3 回归和完成报告 | 未开始 |

### V4.3-A：建立检索失败归因基线

**目的：** 把真实 eval 失败从“失败 case”拆成可行动的检索问题类型。

#### A1. 新增检索失败分类模型

- 修改文件：
  - 新增 `backend/app/evaluation/retrieval_diagnostics.py`
  - 新增 `tests/unit/test_retrieval_diagnostics.py`
- 实现的类/函数：
  - `RetrievalFailureCategory`
  - `RetrievalFailureItem`
  - `classify_retrieval_failure(case: dict, result: dict) -> RetrievalFailureItem`
  - `summarize_retrieval_failures(items: list[RetrievalFailureItem]) -> dict`
- 验收标准：
  - 至少区分 `NO_HIT`、`LOW_RELEVANCE`、`WRONG_SOURCE`、`MISSING_CITATION`、`UNSUPPORTED_ANSWER`、`NO_ANSWER_FALSE_POSITIVE`。
  - 分类结果能写入 real eval summary。
  - 不改变现有通过 case 的判定逻辑。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_retrieval_diagnostics.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.3-A1：新增真实检索失败归因模型"
  ```

#### A2. 生成 V4.3 检索质量基线报告

- 修改文件：
  - 修改 `backend/app/evaluation/real_rag_runner.py`
  - 新增 `docs/V4_3_RETRIEVAL_BASELINE.md`
  - 新增/修改 `tests/integration/test_eval_runner.py`
- 实现的类/函数：
  - `RealRagEvalRunner._write_retrieval_diagnostics(...)`
  - `build_retrieval_baseline_markdown(report: dict) -> str`
- 验收标准：
  - `reports\real_v4_3\retrieval_diagnostics.md` 包含失败类别、case_id、query、预期 source、实际 source。
  - baseline 文档明确哪些问题属于 Agentic RAG 应用层，哪些可能需要 RAG-SERVER 配置调优。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py tests/unit/test_retrieval_diagnostics.py -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_3
  ```
- commit：
  ```powershell
  git commit -m "V4.3-A2：生成检索质量基线报告"
  ```

### V4.3-B：查询改写与双语归一化

**目的：** 在不修改 RAG-SERVER 内核的前提下，提升真实畜牧问题的查询表达质量。

#### B1. 新增真实 RAG 查询归一化策略

- 修改文件：
  - 新增 `backend/app/integrations/rag_server/query_rewriter.py`
  - 新增 `tests/unit/test_rag_query_rewriter.py`
- 实现的类/函数：
  - `RagQueryRewriteResult`
  - `rewrite_livestock_query(query: str, *, language_hint: str | None = None) -> RagQueryRewriteResult`
  - `extract_livestock_terms(query: str) -> list[str]`
- 验收标准：
  - 中文“犊牛拉稀”可补充英文同义词 `calf diarrhea/scours`。
  - 英文 calf scours 可补充中文同义词“犊牛腹泻”。
  - 高风险用药问题不被改写成可直接回答的处方问题。
  - 保留原始 query，trace 中能看到 rewritten query。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_rag_query_rewriter.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.3-B1：新增畜牧查询双语归一化"
  ```

#### B2. 将 query rewrite 接入真实 RAG adapter

- 修改文件：
  - 修改 `backend/app/integrations/rag_server/mcp_stdio_client.py`
  - 修改 `backend/app/core/config.py`
  - 修改 `config/settings.yaml`
  - 新增/修改 `tests/integration/test_rag_server_adapter.py`
- 实现的类/函数：
  - `RagServerSettings.query_rewrite_enabled`
  - `RagServerMcpClient.search(...)`
  - `build_query_rewrite_trace(...)`
- 验收标准：
  - 默认关闭或 shadow 记录，不破坏 V4.2 回归。
  - 开启后真实 RAG 请求使用 rewritten query，同时保留 original query。
  - trace 中包含 rewrite reason 和 terms。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_rag_server_adapter.py tests/unit/test_config.py -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --golden-set tests\fixtures\real_golden_v4_2\bilingual.json --output-dir reports\real_v4_3_bilingual
  ```
- commit：
  ```powershell
  git commit -m "V4.3-B2：接入真实 RAG 查询改写"
  ```

### V4.3-C：citation/source ranking 质量策略

**目的：** 优先暴露高质量来源，降低低质量或弱相关来源对答案的影响。

#### C1. 新增来源质量评分

- 修改文件：
  - 修改 `backend/app/evaluation/source_manifest.py`
  - 新增 `backend/app/integrations/rag_server/source_quality.py`
  - 新增 `tests/unit/test_source_quality.py`
- 实现的类/函数：
  - `SourceQualityScore`
  - `score_source_quality(source_id: str, manifest: SourceManifest) -> SourceQualityScore`
  - `rank_hits_by_source_quality(hits: list[RagSearchHit], manifest: SourceManifest) -> list[RagSearchHit]`
- 验收标准：
  - 官方、大学 Extension、国际组织优先级高于 reference-only 和版权风险来源。
  - redteam/reference 来源不得作为普通知识回答的首选引用，除非 case 明确允许。
  - 排序策略可关闭，默认不影响 fake 回归。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_source_quality.py tests/unit/test_source_manifest.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.3-C1：新增来源质量评分策略"
  ```

#### C2. 在 real eval 中统计来源质量

- 修改文件：
  - 修改 `backend/app/evaluation/metrics.py`
  - 修改 `backend/app/evaluation/real_rag_runner.py`
  - 新增/修改 `tests/unit/test_eval_metrics.py`
- 实现的类/函数：
  - `compute_source_quality_metrics(...)`
  - `RealRagEvalRunner._write_summary(...)`
- 验收标准：
  - summary 包含 high_quality_source_rate、reference_only_citation_count、unknown_source_count。
  - source quality 下降时能在 report diff 中看到。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_eval_metrics.py tests/integration/test_eval_runner.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.3-C2：统计真实回答来源质量"
  ```

### V4.3-D：RAG-SERVER 配置建议报告

**目的：** 如果应用层查询和阈值仍不能解决问题，输出可人工执行的 RAG-SERVER 调优建议，但不自动改 RAG-SERVER。

#### D1. 新增 RAG-SERVER 调优建议文档生成

- 修改文件：
  - 新增 `backend/app/evaluation/rag_server_tuning_advice.py`
  - 新增 `docs/V4_3_RAG_SERVER_TUNING_ADVICE.md`
  - 新增 `tests/unit/test_rag_server_tuning_advice.py`
- 实现的类/函数：
  - `build_tuning_advice(diagnostics: dict, failures: list[RetrievalFailureItem]) -> str`
  - `classify_tuning_need(failures: list[RetrievalFailureItem]) -> list[str]`
- 验收标准：
  - 只输出建议，不改配置。
  - 建议区分 collection 资料不足、embedding 表达弱、rerank 缺失、chunk 过粗/过细。
  - 如需要用户配置 API key 或模型，明确要求用户人工确认。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_rag_server_tuning_advice.py -q
  git diff --check docs/V4_3_RAG_SERVER_TUNING_ADVICE.md
  ```
- commit：
  ```powershell
  git commit -m "V4.3-D1：生成 RAG-SERVER 调优建议"
  ```

### V4.3-E：V4.3 回归和完成报告

- 修改文件：
  - 新增 `docs/V4_3_COMPLETION_REPORT.md`
  - 修改 `DEV_SPEC_v4_2.md`
- 实现的类/函数：无
- 验收标准：
  - V4.2 quality gate 不下降。
  - bilingual real eval 明确改善或记录未改善原因。
  - 检索失败分类报告完整。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest -m "not rag_server" -q
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_3
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage gate --report reports\real_v4_3\eval_result.json
  ```
- commit：
  ```powershell
  git commit -m "V4.3-E：完成检索质量优化阶段"
  ```

## 11. V4.4：本地产品体验工作台

### 11.1 阶段目的

V4.4 的目标是把当前静态 demo 升级为本地工作台，让开发者和用户能直接查看知识库状态、真实评测报告、trace、引用来源、安全拒答和人工复核任务。V4.4 仍保持轻量级，不引入 React/Vue/数据库服务。

### 11.2 进度跟踪表

| 子阶段 | 目的 | 状态 |
|---|---|---|
| V4.4-A | 工作台信息架构和 API contract | 未开始 |
| V4.4-B | 知识库与 batch 状态页 | 未开始 |
| V4.4-C | 评测报告查看页 | 未开始 |
| V4.4-D | Trace 和引用复核页 | 未开始 |
| V4.4-E | 前端回归和完成报告 | 未开始 |

### V4.4-A：工作台信息架构和 API contract

#### A1. 新增工作台 API contract 文档

- 修改文件：
  - 新增 `docs/V4_4_WORKBENCH_SPEC.md`
  - 修改 `docs/API_SPEC.md`
- 实现的类/函数：无
- 验收标准：
  - 明确工作台包含 Knowledge、Evaluation、Trace、Review 四个 tab。
  - 明确所有接口只读，V4.4 不提供删除或真实入库操作按钮。
  - API 不暴露 API key、RAG-SERVER 私有配置明文。
- 测试方法：
  ```powershell
  git diff --check docs/V4_4_WORKBENCH_SPEC.md docs/API_SPEC.md
  ```
- commit：
  ```powershell
  git commit -m "V4.4-A1：定义本地工作台接口规范"
  ```

#### A2. 新增工作台只读 API

- 修改文件：
  - 新增 `backend/app/api/workbench.py`
  - 修改 `backend/app/main.py`
  - 新增 `tests/integration/test_workbench_api.py`
- 实现的类/函数：
  - `get_workbench_status(request: Request) -> dict`
  - `list_corpus_batches(request: Request) -> dict`
  - `list_eval_reports(request: Request) -> dict`
  - `get_eval_report(report_id: str) -> dict`
- 验收标准：
  - `/api/workbench/status` 返回 rag_mode、collection、batch、quality gate。
  - 报告接口只读取 `reports/` 或 `.tmp_tests/` 中允许路径，不允许任意路径读取。
  - 未配置真实 RAG 时返回 `not_configured`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_workbench_api.py tests/integration/test_api_contract.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.4-A2：新增本地工作台只读 API"
  ```

### V4.4-B：知识库与 batch 状态页

#### B1. 前端新增 Knowledge tab

- 修改文件：
  - 修改 `backend/app/static/frontend/app.js`
  - 修改 `backend/app/static/frontend/styles.css`
  - 新增/修改 `tests/integration/test_frontend_contract.py`
- 实现的类/函数：
  - `renderKnowledgeTab(state)`
  - `fetchWorkbenchStatus()`
  - `renderBatchList(batches)`
- 验收标准：
  - 显示当前 collection、batch id、source count、manifest path、quality gate。
  - 不显示 API key 和 RAG-SERVER 私有配置值。
  - 移动端不重叠，表格可横向滚动或折叠。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.4-B1：新增知识库状态页"
  ```

### V4.4-C：评测报告查看页

#### C1. 前端展示 eval summary

- 修改文件：
  - 修改 `backend/app/static/frontend/app.js`
  - 修改 `backend/app/static/frontend/styles.css`
  - 新增/修改 `tests/integration/test_frontend_contract.py`
- 实现的类/函数：
  - `renderEvaluationTab(reports)`
  - `renderMetricSummary(metrics)`
  - `renderFailureCategories(categories)`
- 验收标准：
  - 展示 pass rate、no-answer、source_uri、safety、mapping warnings。
  - skipped real eval 明确显示 skipped reason。
  - failure categories 可读，不需要打开 raw JSON。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py tests/integration/test_workbench_api.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.4-C1：前端展示真实评测摘要"
  ```

### V4.4-D：Trace 和引用复核页

#### D1. 增加引用复核数据模型

- 修改文件：
  - 新增 `backend/app/services/review_queue_service.py`
  - 新增 `tests/unit/test_review_queue_service.py`
- 实现的类/函数：
  - `ReviewQueueItem`
  - `build_review_items_from_eval(report: dict) -> list[ReviewQueueItem]`
  - `filter_review_items(items: list[ReviewQueueItem], status: str | None) -> list[ReviewQueueItem]`
- 验收标准：
  - 从 eval failed cases 生成复核项。
  - 每项包含 case_id、query、answer、source_uri、failure_category。
  - V4.4 只读展示，不做持久化人工状态修改。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_review_queue_service.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.4-D1：生成评测失败复核队列"
  ```

#### D2. 前端展示 Trace/Review tab

- 修改文件：
  - 修改 `backend/app/api/workbench.py`
  - 修改 `backend/app/static/frontend/app.js`
  - 修改 `backend/app/static/frontend/styles.css`
  - 新增/修改 `tests/integration/test_workbench_api.py`
- 实现的类/函数：
  - `list_review_items(request: Request) -> dict`
  - `renderTraceTab(trace)`
  - `renderReviewTab(items)`
- 验收标准：
  - 可查看 request_id 对应 agent path、RAG mode、collection、mapping warnings。
  - failed eval case 可看到引用来源和失败类别。
  - 不提供会修改数据的操作。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_workbench_api.py tests/integration/test_frontend_contract.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.4-D2：前端展示 trace 和复核队列"
  ```

### V4.4-E：前端回归和完成报告

- 修改文件：
  - 新增 `docs/V4_4_COMPLETION_REPORT.md`
  - 修改 `README.md`
  - 修改 `docs/DEMO_SCRIPT.md`
- 实现的类/函数：无
- 验收标准：
  - `/app` 可以完成 Chat、Knowledge、Evaluation、Trace、Review 基本浏览。
  - 前端 contract 测试通过。
  - 默认非真实 RAG 回归通过。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py tests/integration/test_workbench_api.py -q
  .venv\Scripts\python.exe -m pytest -m "not rag_server" -q
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
  ```
- commit：
  ```powershell
  git commit -m "V4.4-E：完成本地工作台体验阶段"
  ```

## 12. V4.5：长期记忆读取闭环

### 12.1 阶段目的

V4.5 的目标是让 Memory 从“只写入用户确认事实的 MVP”升级为“可控读取并参与回答的上下文能力”。V4.5 不写入 AI 诊断结论，不把记忆当作医学事实来源，不绕过 RAG citation 和 safety guard。

### 12.2 进度跟踪表

| 子阶段 | 目的 | 状态 |
|---|---|---|
| V4.5-A | 记忆读取策略和安全边界 | 未开始 |
| V4.5-B | Memory retrieval service | 未开始 |
| V4.5-C | Chat/agent 接入记忆上下文 | 未开始 |
| V4.5-D | 用户可查看和删除记忆 | 未开始 |
| V4.5-E | 记忆评测与完成报告 | 未开始 |

### V4.5-A：记忆读取策略和安全边界

#### A1. 编写长期记忆读取规范

- 修改文件：
  - 新增 `docs/V4_5_MEMORY_READ_SPEC.md`
  - 修改 `docs/SAFETY_SPEC.md`
- 实现的类/函数：无
- 验收标准：
  - 只有 `source=user_confirmed` 的事实可用于回答上下文。
  - AI 诊断、模型推断、RAG 摘要不得写入长期记忆。
  - 记忆只能作为用户上下文，不替代 RAG evidence 和兽医建议。
  - 用户必须能查看和删除长期记忆。
- 测试方法：
  ```powershell
  git diff --check docs/V4_5_MEMORY_READ_SPEC.md docs/SAFETY_SPEC.md
  ```
- commit：
  ```powershell
  git commit -m "V4.5-A1：定义长期记忆读取安全边界"
  ```

#### A2. 扩展 memory 配置

- 修改文件：
  - 修改 `backend/app/core/config.py`
  - 修改 `config/settings.yaml`
  - 新增/修改 `tests/unit/test_config.py`
- 实现的类/函数：
  - `LongTermMemorySettings.read_enabled`
  - `LongTermMemorySettings.max_context_items`
  - `LongTermMemorySettings.allowed_fact_sources`
- 验收标准：
  - 默认 `read_enabled=false`。
  - 默认只允许 `user_confirmed`。
  - 配置缺省兼容旧 settings。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_config.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-A2：扩展长期记忆读取配置"
  ```

### V4.5-B：Memory retrieval service

#### B1. 新增记忆检索服务

- 修改文件：
  - 修改 `backend/app/services/memory_service.py`
  - 新增 `tests/unit/test_memory_retrieval_service.py`
- 实现的类/函数：
  - `MemoryContextItem`
  - `retrieve_memory_context(subject_id: str, query: str, *, limit: int) -> list[MemoryContextItem]`
  - `filter_safe_memory_facts(facts: list[MemoryFact]) -> list[MemoryFact]`
- 验收标准：
  - 只返回未过期、来源允许、与 subject_id 匹配的事实。
  - 返回项包含 fact_id、fact_type、value、source、created_at、expires_at。
  - 不返回 AI 诊断类事实。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_memory_service.py tests/unit/test_memory_retrieval_service.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-B1：新增长期记忆检索服务"
  ```

#### B2. 增加 memory repository 查询能力

- 修改文件：
  - 修改 `backend/app/db/repositories.py`
  - 新增/修改 `tests/integration/test_memory_repository.py`
- 实现的类/函数：
  - `MemoryRepository.list_facts_by_subject(...)`
  - `MemoryRepository.delete_fact(fact_id: str) -> bool`
- 验收标准：
  - 可按 subject_type、subject_id、fact_type 查询。
  - 删除是显式用户操作，不做自动批量删除。
  - 查询和删除均有测试覆盖。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_memory_repository.py tests/integration/test_memory_schema.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-B2：补齐长期记忆查询和删除仓储能力"
  ```

### V4.5-C：Chat/agent 接入记忆上下文

#### C1. Disease/measurement 路径读取记忆

- 修改文件：
  - 修改 `backend/app/agent/graph.py`
  - 修改 `backend/app/services/chat_service.py`
  - 新增/修改 `tests/e2e/test_memory_flow.py`
- 实现的类/函数：
  - `attach_memory_context(state: MultiAgentState, memory_items: list[MemoryContextItem]) -> None`
  - `run_disease_graph(...)`
  - `run_measurement_graph(...)`
- 验收标准：
  - 只有 `long_term_memory.read_enabled=true` 时读取。
  - 读取结果进入 trace/debug，不直接覆盖用户本轮输入。
  - 记忆上下文只能补充已确认事实，例如动物 ID、历史体尺、用户确认症状。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/e2e/test_memory_flow.py tests/integration/test_agent_graph.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-C1：在 agent graph 中读取长期记忆上下文"
  ```

#### C2. 回答中标注记忆来源

- 修改文件：
  - 修改 `backend/app/agent/response_agent.py`
  - 修改 `backend/app/services/chat_service.py`
  - 新增/修改 `tests/unit/test_response_agent.py`
- 实现的类/函数：
  - `render_memory_context_notice(...)`
  - `state_to_chat_data(...)`
- 验收标准：
  - API data 中包含 `memory_context_used` 和 `memory_sources`。
  - 最终回答能区分“根据你确认的历史记录”和“根据知识库资料”。
  - 高风险医疗建议仍必须引用 RAG 或拒答，不能只靠记忆给结论。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_response_agent.py tests/e2e/test_memory_flow.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-C2：在回答中标注长期记忆来源"
  ```

### V4.5-D：用户可查看和删除记忆

#### D1. 新增 memory API

- 修改文件：
  - 新增 `backend/app/api/memory.py`
  - 修改 `backend/app/main.py`
  - 新增 `tests/integration/test_memory_api.py`
- 实现的类/函数：
  - `list_memory_facts(subject_type: str, subject_id: str) -> dict`
  - `delete_memory_fact(fact_id: str) -> dict`
- 验收标准：
  - 可查看指定 animal/farm 的记忆事实。
  - 可删除单条事实。
  - API 返回中不包含内部 SQL 细节。
  - 删除不存在 fact 返回可读错误。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_memory_api.py tests/integration/test_api_contract.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-D1：新增长期记忆查看和删除 API"
  ```

#### D2. 前端 Memory tab

- 修改文件：
  - 修改 `backend/app/static/frontend/app.js`
  - 修改 `backend/app/static/frontend/styles.css`
  - 新增/修改 `tests/integration/test_frontend_contract.py`
- 实现的类/函数：
  - `renderMemoryTab(...)`
  - `fetchMemoryFacts(subject)`
  - `deleteMemoryFact(factId)`
- 验收标准：
  - 用户能查看 animal/farm 记忆。
  - 删除操作有确认，不误删。
  - 页面明确显示事实来源和更新时间。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py tests/integration/test_memory_api.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-D2：前端新增长期记忆管理页"
  ```

### V4.5-E：记忆评测与完成报告

#### E1. 新增长期记忆评测集

- 修改文件：
  - 新增 `tests/fixtures/memory_v4_5_cases.json`
  - 修改 `backend/app/evaluation/v3_runner.py`
  - 新增/修改 `tests/integration/test_memory_eval.py`
- 实现的类/函数：
  - `MemoryEvalCase`
  - `run_memory_eval_case(...)`
  - `compute_memory_metrics(...)`
- 验收标准：
  - 覆盖读取成功、读取关闭、事实过期、事实冲突、删除后不可用。
  - 验证 AI 诊断不会被当作长期事实读取。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_memory_eval.py tests/e2e/test_memory_flow.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-E1：新增长期记忆读取评测"
  ```

#### E2. V4.5 全量回归和完成报告

- 修改文件：
  - 新增 `docs/V4_5_COMPLETION_REPORT.md`
  - 修改 `README.md`
  - 修改 `docs/HARNESS.md`
  - 修改 `DEV_SPEC_v4_2.md`
- 实现的类/函数：无
- 验收标准：
  - 默认 memory read 关闭时 V2/V3/V4.2 回归不破。
  - memory read 开启时，记忆上下文可解释、可删除、可追踪。
  - 安全红队仍通过。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest -m "not rag_server" -q
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  .venv\Scripts\python.exe scripts\check_v3.py --stage full
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
  .venv\Scripts\python.exe -m pytest tests/integration/test_memory_api.py tests/integration/test_memory_eval.py tests/e2e/test_memory_flow.py -q
  ```
- commit：
  ```powershell
  git commit -m "V4.5-E2：完成长期记忆读取闭环阶段"
  ```

## 13. V4 总体完成定义

V4 全部完成必须同时满足：

- V4.2：真实知识库 batch、manifest、real eval、quality gate 完成。
- V4.3：检索失败归因、双语查询改写、来源质量统计、RAG-SERVER 调优建议完成。
- V4.4：本地工作台可以展示知识库、评测、trace 和复核队列。
- V4.5：长期记忆可控读取、可解释、可删除，且默认关闭时不影响旧路径。
- 默认测试通过：
  ```powershell
  .venv\Scripts\python.exe -m pytest -m "not rag_server" -q
  ```
- V2/V3/V4.2 检查通过：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  .venv\Scripts\python.exe scripts\check_v3.py --stage full
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
  ```
- 真实 RAG 可用时，真实 batch eval 和 quality gate 通过：
  ```powershell
  $env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
  .venv\Scripts\python.exe -m pytest -m rag_server -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --batch docs\rag_corpus\batches\batch_002.yaml --golden-set tests\fixtures\real_golden_v4_2\all.json --output-dir reports\real_v4_final
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage gate --report reports\real_v4_final\eval_result.json
  ```
- 每个子阶段均有简体中文 commit。

## 14. V4 之后的方向

V4.2-V4.5 完成后，才建议进入 V5：

| 阶段 | 主题 | 进入前提 |
|---|---|---|
| V5.0 | 真实本地模型接入 | V4 real eval 稳定，memory read 安全边界稳定，用户确认硬件和模型。 |
| V5.1 | LoRA 训练闭环 | LoRA 数据治理已可审计，训练数据脱敏和质量检查通过。 |
| V5.2 | ModelRouter 有限 takeover | 本地模型在低风险结构化任务上通过独立评测，不影响 final safety。 |
