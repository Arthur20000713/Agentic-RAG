# DEV_SPEC_V5：本地模型、LoRA 与 ModelRouter 正式启用

> 本文档承接 `DEV_SPEC_v4_2.md`。默认前提是 V4.2-V4.5 已完成：真实知识库可规模化管理、真实 RAG 质量门禁稳定、本地工作台可用、长期记忆可控读取。V5 的目标是把当前 mock/影子阶段的模型能力落地为真实本地推理、真实 LoRA 训练和可控的 ModelRouter 低风险接管。

## 0. 阶段定位

### 0.1 V5 要解决的问题

当前仓库已有以下基础：

- `LocalModelClient` 存在，但 `provider="mock"`，只支持结构化 JSON mock，不是真实本地模型。
- `ModelRouter` 已有 shadow/takeover 骨架，但默认关闭，不能直接视为生产启用。
- LoRA 已有数据治理 dry-run、脱敏导出和 `ModelRegistry`，但没有真实训练、评估和推理接入。
- V3/V4 阶段已建立安全、真实 RAG、评测、trace、memory 和工作台基础。

V5 要解决的是：

- 接入真实本地模型推理后端。
- 让本地模型先稳定承担低风险结构化任务。
- 让 ModelRouter 从 shadow 进入有限 takeover。
- 建立 LoRA 真实训练、注册、评估和灰度启用流程。
- 建立本地模型和 LoRA 的安全门禁、回退和最终收口文档。

### 0.2 V5 不做什么

- 不做多用户登录、权限体系。
- 不做互联网工业部署。
- 不做生产级备份、恢复、监控、告警。
- 不让本地模型直接接管高风险兽医诊断、处方、药物剂量、停药期或确定性治疗建议。
- 不用 LoRA 训练数据包含 API key、原始 RAG 全文、版权受限全文、用户敏感信息。
- 不为了通过测试而回退 fake 或 mock 并伪装成真实本地模型。

## 1. 项目概述

### 1.1 设计理念

V5 的设计原则是“先真实接入，再小范围接管，最后训练增强”。真实本地模型接入后，必须先经过 shadow 对比和安全门禁，只允许接管低风险、结构化、可验证的任务。LoRA 只在数据治理、训练日志、模型注册和离线评测都通过后，才能灰度参与推理。

### 1.2 项目定位

V5 完成后，本项目应具备完整的本地优先 Agentic RAG 能力：

- 真实 RAG 负责知识证据。
- 本地模型负责低风险结构化任务、查询改写、槽位抽取、体尺 JSON 和摘要草稿。
- ModelRouter 负责根据任务类型、安全等级和质量门禁决定 primary/local/lora 路由。
- LoRA 负责在特定低风险任务上提升本地模型效果。
- Safety 和 Verifier 仍是最终边界，不能被本地模型或 LoRA 绕过。

## 2. 核心特点

| 特点 | 说明 |
|---|---|
| 真实本地推理 | 支持 Ollama/vLLM/llama.cpp 这类本地后端，替代 mock local model。 |
| 低风险接管 | ModelRouter 只允许本地模型接管结构化、低风险、无需最终医疗结论的任务。 |
| LoRA 闭环 | 包含数据导出、脱敏、训练、注册、离线评估和灰度启用。 |
| 安全门禁 | 高风险任务保持 primary/RAG/safety 路径，不开放本地模型直接回答。 |
| 可回退 | 本地模型失败、超时、输出 schema 不合格时自动回退 primary 路径。 |
| 可观测 | 所有路由、模型、延迟、失败、回退、LoRA 版本写入 trace/report。 |

## 3. 技术选型

| 类别 | 选型 | 约束 |
|---|---|---|
| 语言 | Python 3.11+ | 使用项目根目录 `.venv`。 |
| 测试 | pytest | 单元、集成、E2E、真实本地模型 optional 分层执行。 |
| 本地模型后端 | Ollama 优先，兼容 vLLM/llama.cpp 扩展 | 默认不要求联网，不自动下载模型。 |
| 配置 | YAML + 环境变量 | 模型 endpoint、model id、timeout、enabled 均配置驱动。 |
| LoRA 训练 | 本地脚本编排 | 可调用外部训练命令，但不把大模型权重提交仓库。 |
| 模型注册 | JSON registry | 记录 adapter path、metrics、任务类型、启用状态。 |
| 报告 | Markdown/JSON/CSV | 适合本地审阅和 git diff。 |

## 4. 开发流程硬约束

### 4.1 虚拟环境

所有 Agentic RAG 侧开发、测试和脚本运行必须使用：

```powershell
.venv\Scripts\python.exe
```

示例：

```powershell
.venv\Scripts\python.exe -m pytest -m "not local_model" -q
.venv\Scripts\python.exe scripts\check_v5.py --stage full
```

真实本地模型后端如需独立服务，由用户人工启动或配置。缺少模型、endpoint、显存或训练环境时，必须询问用户，不得用 mock 冒充真实能力。

### 4.2 commit 规则

每个约 1 小时可验收增量完成并通过对应测试后，必须提交简体中文 commit：

```powershell
git add <本小阶段修改文件>
git commit -m "V5.0-A1：定义真实本地模型客户端接口"
```

禁止提交：

- `.venv/`
- `.tmp_tests/`
- `data/`
- `reports/`
- 模型权重、LoRA adapter 大文件
- API key、token、私有 endpoint 密钥
- 未脱敏训练数据
- RAG-SERVER 私有配置

### 4.3 模型接入边界

- `provider=mock` 只能用于测试，不得作为 V5 完成依据。
- 真实本地模型 optional 测试不可用时可以 skipped，但必须写明原因。
- `final_answer` 默认不允许本地模型 takeover。
- `S3/S4` 高风险任务必须走 primary/safety，不允许本地模型接管。
- LoRA 推理默认关闭，只有 registry、评测和 safety gate 均通过后才能灰度启用。

## 5. 测试方案

### 5.1 TDD 流程

1. 先写失败测试或新增 eval case。
2. 运行目标测试确认失败。
3. 实现最小功能。
4. 运行目标测试和相关回归。
5. 如涉及真实模型，运行 optional smoke/eval。
6. 更新文档和报告。
7. 简体中文 commit。

### 5.2 分层测试

| 层级 | 内容 | 命令 |
|---|---|---|
| 单元测试 | local client、schema validation、router policy、LoRA registry、quality gate | `.venv\Scripts\python.exe -m pytest tests/unit -q` |
| 集成测试 | model backend adapter、route log、eval runner、LoRA scripts | `.venv\Scripts\python.exe -m pytest tests/integration -q` |
| E2E 测试 | `/api/chat`、V3 graph、memory、frontend debug | `.venv\Scripts\python.exe -m pytest tests/e2e -q` |
| 默认回归 | 不依赖真实本地模型和真实 RAG | `.venv\Scripts\python.exe -m pytest -m "not local_model and not rag_server" -q` |
| 本地模型 smoke | 真实本地模型 endpoint 可用时运行 | `.venv\Scripts\python.exe -m pytest -m local_model -q` |
| V5 eval | 本地模型/Router/LoRA 质量评测 | `.venv\Scripts\python.exe scripts\run_eval.py --mode v5 --optional --output-dir reports\v5` |

### 5.3 V5 质量门禁

| 指标 | 最低要求 | 说明 |
|---|---:|---|
| local_model_schema_valid_rate | `>= 0.98` | 本地模型结构化输出必须稳定。 |
| local_model_timeout_rate | `<= 0.02` | 超时必须可控。 |
| router_fallback_success_rate | `1.00` | 本地失败后必须成功回退。 |
| low_risk_takeover_pass_rate | `>= 0.95` | 低风险接管任务质量。 |
| safety_redteam_pass_rate | `1.00` | 高风险任务不得被本地模型误接管。 |
| lora_eval_pass_rate | `>= 0.95` | LoRA 启用前的离线任务评测。 |
| regression_pass_rate | `1.00` | V2/V3/V4 默认回归不能下降。 |

## 6. 系统架构与模块设计

### 6.1 整体架构图

```text
                 +------------------+
                 | FastAPI /api/*   |
                 +--------+---------+
                          |
                          v
                 +------------------+
                 | V3 Agent Graph   |
                 +--------+---------+
                          |
                          v
                 +------------------+
                 | SafetyPrecheck   |
                 +--------+---------+
                          |
                          v
                 +------------------+
                 | ModelRouter      |
                 +---+----------+---+
                     |          |
          primary    |          | local takeover/shadow
                     |          v
                     |   +---------------------+
                     |   | LocalModelClient    |
                     |   | Ollama/vLLM/llama   |
                     |   +----------+----------+
                     |              |
                     |              v
                     |   +---------------------+
                     |   | LoRA adapter        |
                     |   | optional / gated    |
                     |   +---------------------+
                     |
                     v
            +---------------------+
            | RAG + Verifier      |
            | Safety + Response   |
            +---------------------+
```

### 6.2 目录结构树

```text
Agentic RAG/
├── DEV_SPEC_V5.md
├── backend/
│   └── app/
│       ├── core/
│       │   └── config.py
│       ├── model/
│       │   ├── base.py
│       │   ├── local_client.py
│       │   ├── local_backends.py          # V5 新增
│       │   ├── local_schema.py            # V5 新增
│       │   ├── router.py
│       │   └── router_policy.py           # V5 新增
│       ├── lora/
│       │   ├── dataset.py
│       │   ├── registry.py
│       │   ├── trainer.py                 # V5 新增
│       │   ├── evaluator.py               # V5 新增
│       │   └── inference.py               # V5 新增
│       ├── evaluation/
│       │   ├── v5_runner.py               # V5 新增
│       │   ├── model_quality_gate.py      # V5 新增
│       │   └── metrics.py
│       └── services/
│           └── trace_service.py
├── scripts/
│   ├── check_v5.py                        # V5 新增
│   ├── run_local_model_smoke.py           # V5 新增
│   ├── train_lora_adapter.py              # V5 新增
│   ├── evaluate_lora_adapter.py           # V5 新增
│   └── run_eval.py
├── tests/
│   ├── fixtures/
│   │   ├── v5_local_model_cases.json
│   │   ├── v5_router_cases.json
│   │   └── v5_lora_cases.json
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── docs/
    ├── V5_LOCAL_MODEL_GUIDE.md
    ├── V5_ROUTER_POLICY.md
    ├── V5_LORA_TRAINING_GUIDE.md
    └── V5_COMPLETION_REPORT.md
```

### 6.3 模块职责说明

| 模块 | 职责 |
|---|---|
| `backend/app/model/local_backends.py` | 封装 Ollama/vLLM/llama.cpp 本地推理后端调用。 |
| `backend/app/model/local_schema.py` | 校验本地模型 JSON 输出、超时、fallback_required。 |
| `backend/app/model/router_policy.py` | 将低风险接管规则从 router 中拆出，便于测试和审计。 |
| `backend/app/lora/trainer.py` | 编排本地 LoRA 训练命令和训练报告。 |
| `backend/app/lora/evaluator.py` | 对 LoRA adapter 做离线任务评测。 |
| `backend/app/lora/inference.py` | 按 registry 和 gate 接入 LoRA 推理。 |
| `backend/app/evaluation/v5_runner.py` | 运行本地模型、router、LoRA 专项评测。 |
| `backend/app/evaluation/model_quality_gate.py` | 根据 V5 指标判断是否允许 takeover/LoRA 启用。 |
| `scripts/check_v5.py` | V5 阶段验收入口。 |

### 6.4 配置示例

```yaml
v3:
  enabled: true

local_model:
  enabled: true
  provider: ollama
  endpoint: "http://127.0.0.1:11434"
  model: "qwen2.5:7b-instruct"
  timeout_seconds: 8
  max_retries: 1
  allow_final_answer: false

model_router:
  enabled: true
  shadow_mode: true
  allow_low_risk_takeover: false
  takeover_task_types:
    - structured_extraction
    - measurement_analysis
    - summarization
  blocked_safety_levels:
    - S3
    - S4

lora:
  dataset_enabled: true
  inference_enabled: false
  registry_path: data/v3/model_registry.json
  adapter_root: data/v5/lora_adapters
  min_eval_pass_rate: 0.95
```

## 7. 项目排期

### 进度跟踪表

| 阶段 | 目的 | 状态 |
|---|---|---|
| V5.0 | 真实本地模型接入 | 未开始 |
| V5.1 | ModelRouter 正式低风险接管 | 未开始 |
| V5.2 | LoRA 真实训练闭环 | 未开始 |
| V5.3 | 本地模型评测与安全门禁 | 未开始 |
| V5.4 | 本地优先交付收口 | 未开始 |

## 8. V5.0：真实本地模型接入

### V5.0-A：本地模型配置和客户端接口

#### A1. 扩展 local model 配置

- 修改文件：
  - 修改 `backend/app/core/config.py`
  - 修改 `config/settings.yaml`
  - 新增/修改 `tests/unit/test_config.py`
- 实现的类/函数：
  - `LocalModelSettings.provider`
  - `LocalModelSettings.endpoint`
  - `LocalModelSettings.model`
  - `LocalModelSettings.max_retries`
  - `LocalModelSettings.allow_final_answer`
- 验收标准：
  - 默认仍为 `enabled=false`、`provider=mock`。
  - 缺省配置兼容旧 settings。
  - `allow_final_answer` 默认 false。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_config.py tests/unit/test_feature_flags.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.0-A1：扩展真实本地模型配置"
  ```

#### A2. 新增本地模型后端抽象

- 修改文件：
  - 新增 `backend/app/model/local_backends.py`
  - 新增 `backend/app/model/local_schema.py`
  - 新增 `tests/unit/test_local_model_backend.py`
- 实现的类/函数：
  - `LocalBackendRequest`
  - `LocalBackendResponse`
  - `BaseLocalBackend.generate(...)`
  - `OllamaBackend.generate(...)`
  - `parse_local_json_response(text: str, schema_name: str) -> dict`
- 验收标准：
  - Ollama 请求 payload 可单元测试，不需要真实服务。
  - 非 JSON 输出返回 `fallback_required=true`。
  - 超时、HTTP error、schema error 不抛到业务层，转为结构化失败。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_local_model_backend.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.0-A2：新增本地模型后端抽象"
  ```

### V5.0-B：替换 mock local client 的真实路径

#### B1. LocalModelClient 支持真实 provider

- 修改文件：
  - 修改 `backend/app/model/local_client.py`
  - 新增/修改 `tests/unit/test_local_model_client.py`
- 实现的类/函数：
  - `LocalModelClient.__init__(settings: Settings | None = None)`
  - `LocalModelClient.generate_json(...)`
  - `LocalModelClient._select_backend(...)`
- 验收标准：
  - `provider=mock` 行为保持兼容。
  - `provider=ollama` 调用 `OllamaBackend`。
  - `final_answer` 在 `allow_final_answer=false` 时仍返回 unsupported。
  - 真实 provider 失败时返回 fallback_required。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_local_model_client.py tests/unit/test_local_model_backend.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.0-B1：接入真实本地模型客户端路径"
  ```

#### B2. 本地模型 smoke 脚本

- 修改文件：
  - 新增 `scripts/run_local_model_smoke.py`
  - 新增 `tests/integration/test_local_model_smoke.py`
- 实现的类/函数：
  - `run_smoke(settings: Settings) -> LocalModelSmokeReport`
  - `main(argv: list[str] | None = None) -> int`
- 验收标准：
  - 未配置真实模型时输出 skipped，退出码 0 仅限 `--optional`。
  - 配置真实模型时运行 query_normalization 和 slot_extraction smoke。
  - 报告写入 `reports/local_model_smoke.json`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_local_model_smoke.py -q
  .venv\Scripts\python.exe scripts\run_local_model_smoke.py --optional --output reports\local_model_smoke.json
  ```
- commit：
  ```powershell
  git commit -m "V5.0-B2：新增本地模型 smoke 检查"
  ```

### V5.0-C：V5 检查脚本和文档

- 修改文件：
  - 新增 `scripts/check_v5.py`
  - 新增 `docs/V5_LOCAL_MODEL_GUIDE.md`
  - 新增 `tests/integration/test_check_v5.py`
- 实现的类/函数：
  - `check_local_model_config(root: Path) -> list[str]`
  - `run_local_model_optional_smoke(...) -> int`
  - `main(argv: list[str] | None = None) -> int`
- 验收标准：
  - `--stage local-model` 检查配置、客户端测试和 optional smoke。
  - 默认 `--stage full` 不强制真实模型可用。
  - 文档说明如何配置 Ollama endpoint 和 model，不包含下载命令强依赖。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_v5.py -q
  .venv\Scripts\python.exe scripts\check_v5.py --stage local-model
  ```
- commit：
  ```powershell
  git commit -m "V5.0-C：新增 V5 本地模型检查入口"
  ```

## 9. V5.1：ModelRouter 正式低风险接管

### V5.1-A：拆分并强化路由策略

#### A1. 新增 router policy 模块

- 修改文件：
  - 新增 `backend/app/model/router_policy.py`
  - 修改 `backend/app/model/router.py`
  - 新增/修改 `tests/unit/test_model_router.py`
- 实现的类/函数：
  - `RouterPolicy`
  - `is_local_takeover_allowed(request: ModelRouteRequest, settings: Settings) -> tuple[bool, str | None]`
  - `blocked_by_safety(request: ModelRouteRequest) -> str | None`
- 验收标准：
  - S3/S4 一律阻止本地接管。
  - `requires_final_answer=true` 默认阻止本地接管。
  - 只有 configured task types 可 takeover。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_model_router.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.1-A1：拆分 ModelRouter 接管策略"
  ```

#### A2. 路由日志补充 takeover/fallback

- 修改文件：
  - 修改 `backend/app/db/migrations.py`
  - 修改 `backend/app/db/repositories.py`
  - 新增/修改 `tests/integration/test_model_route_log.py`
- 实现的类/函数：
  - `ModelRouteLogRepository.create(...)`
  - 新增字段 `fallback_required`、`fallback_reason`、`latency_ms`、`model_version`
- 验收标准：
  - shadow、takeover、fallback 都可查询。
  - migration 对已有 SQLite 兼容。
  - trace debug 能看到 route_mode 和 fallback_reason。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_model_route_log.py tests/integration/test_sqlite_schema.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.1-A2：补充模型路由接管和回退日志"
  ```

### V5.1-B：低风险任务 takeover

#### B1. query normalization 接管

- 修改文件：
  - 修改 `backend/app/model/query_normalizer.py`
  - 修改 `backend/app/agent/graph.py`
  - 新增/修改 `tests/unit/test_query_normalizer.py`
  - 新增/修改 `tests/integration/test_agent_graph.py`
- 实现的类/函数：
  - `normalize_query_with_router(...)`
  - `record_local_model_result(...)`
- 验收标准：
  - router shadow 时仍走 primary 结果。
  - router takeover 时可使用本地模型输出。
  - 本地模型 schema invalid 时回退 primary/rule path。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_query_normalizer.py tests/integration/test_agent_graph.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.1-B1：允许本地模型接管查询归一化"
  ```

#### B2. 槽位抽取和体尺 JSON 接管

- 修改文件：
  - 修改 `backend/app/agent/disease_agent.py`
  - 修改 `backend/app/agent/measurement_agent.py`
  - 新增/修改 `tests/unit/test_disease_agent.py`
  - 新增/修改 `tests/unit/test_measurement_agent.py`
- 实现的类/函数：
  - `extract_slots_with_router(...)`
  - `render_measurement_json_with_router(...)`
- 验收标准：
  - 仅 S0/S1/S2 低风险结构化任务允许 takeover。
  - 输出必须通过现有 schema 校验。
  - 高风险 disease final answer 不允许本地 takeover。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_disease_agent.py tests/unit/test_measurement_agent.py tests/unit/test_safety_precheck.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.1-B2：允许本地模型接管低风险结构化任务"
  ```

### V5.1-C：Router 评测和启用文档

- 修改文件：
  - 新增 `tests/fixtures/v5_router_cases.json`
  - 新增 `backend/app/evaluation/v5_runner.py`
  - 修改 `scripts/run_eval.py`
  - 新增 `docs/V5_ROUTER_POLICY.md`
  - 新增/修改 `tests/integration/test_eval_runner.py`
- 实现的类/函数：
  - `V5EvalRunner`
  - `run_router_case(...)`
  - `compute_router_metrics(...)`
- 验收标准：
  - `run_eval.py --mode v5` 可运行 router cases。
  - 输出 takeover rate、fallback rate、blocked high-risk count。
  - 文档列出允许接管和禁止接管任务。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py tests/unit/test_model_router.py -q
  .venv\Scripts\python.exe scripts\run_eval.py --mode v5 --optional --output-dir reports\v5_router
  ```
- commit：
  ```powershell
  git commit -m "V5.1-C：新增 ModelRouter 正式接管评测"
  ```

## 10. V5.2：LoRA 真实训练闭环

### V5.2-A：训练数据集升级

#### A1. LoRA dataset split 和质量报告

- 修改文件：
  - 修改 `scripts/export_lora_dataset.py`
  - 新增 `backend/app/lora/dataset_quality.py`
  - 新增/修改 `tests/unit/test_lora_dataset.py`
- 实现的类/函数：
  - `split_lora_dataset(examples: list[LoraTrainingExample], ratios: dict[str, float]) -> dict[str, list[LoraTrainingExample]]`
  - `build_lora_dataset_quality_report(...)`
- 验收标准：
  - 支持 train/validation/test split。
  - 检查重复 example_id、超长文本、敏感字段、任务分布。
  - 输出 `lora_dataset_report.json`。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_lora_dataset.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.2-A1：升级 LoRA 数据集切分和质量报告"
  ```

#### A2. 脱敏训练数据验收脚本

- 修改文件：
  - 新增 `scripts/check_lora_dataset.py`
  - 新增 `tests/integration/test_lora_dataset_check.py`
- 实现的类/函数：
  - `check_lora_dataset(path: Path) -> list[str]`
  - `main(argv: list[str] | None = None) -> int`
- 验收标准：
  - 发现 forbidden fields 时退出码非 0。
  - 训练数据缺少 test split 时失败。
  - 不打印原始敏感文本。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_lora_dataset_check.py -q
  .venv\Scripts\python.exe scripts\check_lora_dataset.py --input data\v5\lora_dataset\dataset.json --optional
  ```
- commit：
  ```powershell
  git commit -m "V5.2-A2：新增 LoRA 数据集脱敏验收脚本"
  ```

### V5.2-B：训练脚本和注册表

#### B1. LoRA 训练命令编排

- 修改文件：
  - 新增 `backend/app/lora/trainer.py`
  - 新增 `scripts/train_lora_adapter.py`
  - 新增 `tests/unit/test_lora_trainer.py`
- 实现的类/函数：
  - `LoraTrainingConfig`
  - `LoraTrainingReport`
  - `build_training_command(config: LoraTrainingConfig) -> list[str]`
  - `run_lora_training(config: LoraTrainingConfig, *, dry_run: bool) -> LoraTrainingReport`
- 验收标准：
  - 默认 dry-run，只输出命令和配置摘要。
  - 真实训练必须显式 `--execute`。
  - 不把模型权重写入仓库路径。
  - 训练日志不输出敏感数据。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_lora_trainer.py -q
  .venv\Scripts\python.exe scripts\train_lora_adapter.py --config config\lora_training.yaml --dry-run
  ```
- commit：
  ```powershell
  git commit -m "V5.2-B1：新增 LoRA 训练命令编排"
  ```

#### B2. 扩展 ModelRegistry

- 修改文件：
  - 修改 `backend/app/lora/registry.py`
  - 新增/修改 `tests/unit/test_lora_registry.py`
- 实现的类/函数：
  - `ModelRegistryEntry.base_model`
  - `ModelRegistryEntry.training_dataset_hash`
  - `ModelRegistryEntry.eval_report_path`
  - `ModelRegistryEntry.safety_gate_status`
- 验收标准：
  - 旧 registry JSON 兼容。
  - 未通过 safety gate 的 adapter 不能 `enabled_for_inference=true`。
  - registry 记录 adapter path，但不要求 path 在仓库内。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_lora_registry.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.2-B2：扩展 LoRA 模型注册表"
  ```

### V5.2-C：LoRA 评估和推理接入

#### C1. LoRA 离线评估

- 修改文件：
  - 新增 `backend/app/lora/evaluator.py`
  - 新增 `scripts/evaluate_lora_adapter.py`
  - 新增 `tests/unit/test_lora_evaluator.py`
- 实现的类/函数：
  - `LoraEvalCase`
  - `LoraEvalReport`
  - `evaluate_lora_adapter(...)`
  - `compute_lora_metrics(...)`
- 验收标准：
  - 评估 query_normalization、slot_extraction、measurement_formatting。
  - 输出 pass_rate、schema_valid_rate、safety_violation_count。
  - 未达标 adapter 不允许启用。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_lora_evaluator.py -q
  .venv\Scripts\python.exe scripts\evaluate_lora_adapter.py --registry data\v3\model_registry.json --model-id <model_id> --optional
  ```
- commit：
  ```powershell
  git commit -m "V5.2-C1：新增 LoRA 离线评估"
  ```

#### C2. LoRA 推理灰度接入

- 修改文件：
  - 新增 `backend/app/lora/inference.py`
  - 修改 `backend/app/model/local_client.py`
  - 修改 `backend/app/services/feature_flag_service.py`
  - 新增/修改 `tests/unit/test_local_model_client.py`
- 实现的类/函数：
  - `LoraInferenceClient`
  - `select_lora_adapter(task_type: LoraTaskType, registry: ModelRegistry) -> ModelRegistryEntry | None`
  - `LocalModelClient.generate_json(...)`
- 验收标准：
  - `lora.inference_enabled=false` 时不走 LoRA。
  - 只有 registry active 且 safety gate passed 的 adapter 可被选择。
  - LoRA 失败自动回退 base local model 或 primary path。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_local_model_client.py tests/unit/test_lora_registry.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.2-C2：灰度接入 LoRA 推理路径"
  ```

## 11. V5.3：本地模型评测与安全门禁

### V5.3-A：模型质量门禁

#### A1. 新增 model quality gate

- 修改文件：
  - 新增 `backend/app/evaluation/model_quality_gate.py`
  - 新增 `tests/unit/test_model_quality_gate.py`
- 实现的类/函数：
  - `ModelQualityThresholds`
  - `ModelQualityGateResult`
  - `evaluate_model_quality_gate(report: dict, thresholds: ModelQualityThresholds) -> ModelQualityGateResult`
- 验收标准：
  - local model、router、LoRA 指标任一不达标则 failed。
  - skipped smoke 不能作为 passed。
  - 输出失败原因和阈值。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/unit/test_model_quality_gate.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.3-A1：新增本地模型质量门禁"
  ```

#### A2. 接入 `check_v5.py`

- 修改文件：
  - 修改 `scripts/check_v5.py`
  - 新增/修改 `tests/integration/test_check_v5.py`
- 实现的类/函数：
  - `run_model_quality_gate(report_path: Path) -> int`
  - `check_v5_report(output_dir: Path) -> list[str]`
- 验收标准：
  - `--stage gate` 可独立检查 V5 report。
  - gate failed 退出码非 0。
  - `--optional` skipped 报告不被误判为通过。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_check_v5.py tests/unit/test_model_quality_gate.py -q
  .venv\Scripts\python.exe scripts\check_v5.py --stage gate --report reports\v5\eval_result.json
  ```
- commit：
  ```powershell
  git commit -m "V5.3-A2：将本地模型质量门禁接入 V5 检查"
  ```

### V5.3-B：安全红队和回退评测

#### B1. 新增 V5 安全红队集

- 修改文件：
  - 新增 `tests/fixtures/v5_safety_redteam.json`
  - 修改 `backend/app/evaluation/v5_runner.py`
  - 新增/修改 `tests/integration/test_v5_safety_runner.py`
- 实现的类/函数：
  - `run_v5_safety_case(...)`
  - `compute_v5_safety_metrics(...)`
- 验收标准：
  - 覆盖药物剂量、处方、停药期、确诊、替代兽医。
  - 本地模型不得 takeover S3/S4。
  - final answer 仍经过 SafetyAgent/Final Guard。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/integration/test_v5_safety_runner.py tests/unit/test_safety_precheck.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.3-B1：新增 V5 本地模型安全红队评测"
  ```

#### B2. 回退链路 E2E

- 修改文件：
  - 新增 `tests/e2e/test_v5_model_fallback_flow.py`
  - 修改 `backend/app/agent/graph.py`
  - 修改 `backend/app/services/chat_service.py`
- 实现的类/函数：
  - `record_model_fallback(...)`
  - `state_to_chat_data(...)`
- 验收标准：
  - 本地模型超时、schema invalid、adapter missing 均能回退。
  - API response debug 中记录 fallback。
  - 用户最终得到可用回答或安全拒答。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/e2e/test_v5_model_fallback_flow.py tests/integration/test_agent_graph.py -q
  ```
- commit：
  ```powershell
  git commit -m "V5.3-B2：固化本地模型失败回退链路"
  ```

## 12. V5.4：本地优先交付收口

### V5.4-A：本地启动和配置模板

#### A1. 新增 V5 配置模板

- 修改文件：
  - 新增 `config/settings.v5.example.yaml`
  - 新增 `docs/V5_LOCAL_RUNBOOK.md`
- 实现的类/函数：无
- 验收标准：
  - 模板不包含真实 key。
  - 包含 fake、real RAG、本地模型、LoRA、Router takeover 的推荐配置。
  - runbook 说明缺少模型时如何 optional skipped。
- 测试方法：
  ```powershell
  git diff --check config/settings.v5.example.yaml docs/V5_LOCAL_RUNBOOK.md
  ```
- commit：
  ```powershell
  git commit -m "V5.4-A1：新增 V5 本地运行配置模板"
  ```

#### A2. 一键本地检查脚本

- 修改文件：
  - 新增 `scripts/check_release_v5.ps1`
  - 修改 `docs/HARNESS.md`
- 实现的类/函数：无
- 验收标准：
  - 脚本运行默认非真实依赖回归。
  - 真实 RAG、本地模型、LoRA 均需显式参数开启。
  - 输出每类检查结果路径。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v5.py --stage full
  git diff --check scripts/check_release_v5.ps1 docs/HARNESS.md
  ```
- commit：
  ```powershell
  git commit -m "V5.4-A2：新增 V5 本地发布检查脚本"
  ```

### V5.4-B：最终文档和完成报告

#### B1. 更新核心文档

- 修改文件：
  - 修改 `README.md`
  - 修改 `docs/API_SPEC.md`
  - 修改 `docs/EVAL_SPEC.md`
  - 修改 `docs/SAFETY_SPEC.md`
  - 修改 `docs/DEMO_SCRIPT.md`
  - 新增 `docs/V5_COMPLETION_REPORT.md`
- 实现的类/函数：无
- 验收标准：
  - 文档明确 V5 支持真实本地模型、LoRA 和低风险 ModelRouter takeover。
  - 文档明确仍不支持多用户权限和互联网生产部署。
  - 文档明确高风险任务边界。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  git diff --check README.md docs
  ```
- commit：
  ```powershell
  git commit -m "V5.4-B1：更新 V5 最终交付文档"
  ```

#### B2. V5 全量回归和收口

- 修改文件：
  - 修改 `DEV_SPEC_V5.md`
  - 修改 `docs/V5_COMPLETION_REPORT.md`
- 实现的类/函数：无
- 验收标准：
  - 默认非真实依赖测试通过。
  - V2/V3/V4/V5 检查通过。
  - 真实 RAG 可用时 real eval 通过对应 gate。
  - 本地模型可用时 local smoke 和 V5 eval 通过 gate。
  - LoRA adapter 可用时 lora eval 通过 gate；不可用时报告 skipped，不能作为 LoRA 完成证据。
- 测试方法：
  ```powershell
  .venv\Scripts\python.exe -m pytest -m "not rag_server and not local_model" -q
  .venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
  .venv\Scripts\python.exe scripts\check_v3.py --stage full
  .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
  .venv\Scripts\python.exe scripts\check_v5.py --stage full
  .venv\Scripts\python.exe scripts\run_eval.py --mode v5 --optional --output-dir reports\v5
  .venv\Scripts\python.exe scripts\check_v5.py --stage gate --report reports\v5\eval_result.json
  ```
- commit：
  ```powershell
  git commit -m "V5.4-B2：完成 V5 本地模型能力收口"
  ```

## 13. V5 完成定义

V5 完成必须同时满足：

- `LocalModelClient` 支持真实本地 provider，mock 仅保留为测试后端。
- `ModelRouter` 能在配置允许时正式接管低风险结构化任务。
- 高风险任务、本地模型 final answer、处方/剂量/确诊请求均被阻止或回退。
- LoRA 数据集可脱敏导出、切分、训练 dry-run/真实训练、注册、离线评估。
- LoRA 推理只有在 registry active 且 safety gate passed 时才可启用。
- V5 eval report 和 model quality gate 可运行。
- 默认无真实依赖测试通过。
- 真实本地模型可用时 smoke/eval 通过。
- 文档明确不包含多用户权限、互联网部署和生产级运维。
- 每个小阶段都有简体中文 commit。

## 14. V5 后项目收尾建议

V5.4 完成后，项目可以进入最终收尾：

- 写 `PROJECT_COMPLETION_REPORT.md`。
- 打本地 release tag，例如 `v1.0-local-agentic-rag`。
- 清理未跟踪设计文档和临时报告。
- 固化演示脚本、面试讲解和运行手册。
- 将 V6 仅作为远期增强，不纳入当前项目必需范围。

V6 可选方向：

- 多用户权限。
- 局域网或互联网部署。
- 生产级备份、恢复、监控、告警。
- 更复杂的 RAG-SERVER 内核优化。
- 企业级审计和权限隔离。
