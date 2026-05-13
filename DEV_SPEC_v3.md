# DEV_SPEC_v3：畜牧业 Agentic RAG 智能助手 V3-Core 开发规范（项目实况修订版）

> 文件来源：基于 `C:\Users\DELL\Downloads\DEV_SPEC_v3 (1).md` 修订
> 修订依据：当前仓库实际代码、提交历史、`README.md`、`AGENTS.md`、V3 设计文档
> 当前基线：V2.5 已完成，系统已有 FastAPI、Multi-agent、Trace、Session Context、Real RAG optional eval、静态前端
> 默认约束：Python、pytest、SQLite、本地优先、零新增外部服务依赖、每个小阶段通过测试后使用简体中文 commit

---

## 0. 实况修订摘要

GPT 版 V3 DEV_SPEC 的方向基本正确，但存在多处与当前项目不一致的假设。本修订版做以下调整：

| 原 GPT 版假设 | 当前项目实况 | 修订要求 |
|---|---|---|
| `TEST_ROOT=backend/tests` | 当前测试根目录是 `tests/` | 所有命令使用 `tests/`。 |
| `CONFIG_ROOT=configs`、`configs/v3.yaml` | 当前配置根目录是 `config/`，入口是 `config/settings.yaml` | V3 配置扩展到 `backend/app/core/config.py` 和 `config/settings.yaml`。 |
| `check_v3.sh` | 当前项目是 Windows/PowerShell 优先，已有 `scripts/check_v2.py` | V3 使用 `scripts/check_v3.py`，不要新增 bash-only 脚本作为唯一入口。 |
| `.v3_agent.env` 强制路径变量 | 当前仓库路径已稳定，不需要用 env 文件替代真实结构 | 可生成 `docs/V3_REPO_MAP.md`，但代码和测试直接遵守当前路径。 |
| V2 接入点未知 | 当前 V2.5 已完成，接入点明确 | V3 必须接入现有模块，不得并行重写。 |
| fake / mock 可覆盖所有路径 | 用户要求真实 RAG 需要时必须真实接入 | fake 只用于默认回归；涉及 real RAG 验收时必须配置真实 RAG-SERVER，不得静默替代。 |

---

## 1. 当前项目基线

### 1.1 已完成能力

当前仓库已经具备：

- FastAPI 应用入口：[backend/app/main.py](backend/app/main.py)
- V2 RAG 配置：[backend/app/core/config.py](backend/app/core/config.py)、[config/settings.yaml](config/settings.yaml)
- RAG-SERVER adapter：[backend/app/integrations/rag_server/](backend/app/integrations/rag_server/)
- 标准 RAG schema 和 `source_uri`：[backend/app/schemas/rag_server.py](backend/app/schemas/rag_server.py)
- Multi-agent graph：[backend/app/agent/graph.py](backend/app/agent/graph.py)
- Supervisor / RAG / Disease / Measurement / Safety / Verifier / Response agents：[backend/app/agent/](backend/app/agent/)
- Trace service 与 trace API：[backend/app/services/trace_service.py](backend/app/services/trace_service.py)、[backend/app/api/traces.py](backend/app/api/traces.py)
- Session Context：[backend/app/services/session_context_service.py](backend/app/services/session_context_service.py)
- Eval runners：[scripts/run_eval.py](scripts/run_eval.py)、[backend/app/evaluation/](backend/app/evaluation/)
- 静态前端：[backend/app/static/frontend/](backend/app/static/frontend/)
- V2 文档：[docs/](docs/)

当前可用命令：

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server"
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports\fake
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
.venv\Scripts\python.exe scripts\run_eval.py --mode multi_agent --output-dir reports\multi_agent
.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
```

### 1.2 真实 RAG-SERVER 位置

真实 RAG-SERVER 位于：

```text
C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER
```

真实 RAG 验收命令：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
# 如 RAG-SERVER 需要独立 Python，可选：
# $env:RAG_SERVER_PYTHON="C:\path\to\python.exe"
.venv\Scripts\python.exe -m pytest -m rag_server
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
```

规则：

- 不得在需要真实 RAG 的任务中用 fake 结果替代。
- 若真实 RAG-SERVER 缺少 API key、模型配置、知识库数据或 Python 环境，必须询问用户。
- 不得复制、打印或提交 RAG-SERVER 中的真实密钥。
- 不得修改 RAG-SERVER 源码，除非用户明确要求。

---

## 2. V3-Core 定位

V3-Core 不是继续重写 V2，也不是重建 RAG。它是在 V2.5 稳定链路上增加以下工程能力：

```text
Feature Flags
Model Router Shadow Mode
低风险结构化任务路由接管
SafetyPrecheck / S0-S4 taxonomy
Verifier P0 增强
LocalModelClient / LocalLoraModelClient 抽象
LoRA 数据治理 dry-run
Farm / Animal Memory MVP
V3 Eval Harness
Trace / Debug 扩展
```

V3-Core 的目标是让系统可回退、可观测、可审计、可评测，而不是在 P0 阶段证明真实本地模型或真实 LoRA 训练效果。

---

## 3. 技术选型与路径

### 3.1 固定项目路径

| 变量 | 当前真实路径 |
|---|---|
| `PROJECT_ROOT` | 当前 git 根目录 |
| `APP_ROOT` | `backend/app` |
| `TEST_ROOT` | `tests` |
| `SCRIPT_ROOT` | `scripts` |
| `CONFIG_ROOT` | `config` |
| `DOC_ROOT` | `docs` |
| `STATIC_ROOT` | `backend/app/static/frontend` |
| `DATA_ROOT` | `data` |
| `REPORT_ROOT` | `reports` |

V3 不使用 `backend/tests`、`configs/`、`app/` 作为默认路径。若某个子任务需要路径映射文档，只能生成 [docs/V3_REPO_MAP.md](docs/V3_REPO_MAP.md)，不能改变现有项目结构。

### 3.2 虚拟环境规则

本项目在 Windows 上开发，命令必须优先使用：

```powershell
.venv\Scripts\python.exe
```

禁止使用：

```text
python
pytest
source .venv/bin/activate
```

除非明确说明是在 Linux/macOS 环境。Windows 默认命令示例：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports\fake
```

### 3.3 配置扩展规则

V3 配置必须扩展现有：

- [backend/app/core/config.py](backend/app/core/config.py)
- [config/settings.yaml](config/settings.yaml)
- [config/settings.test.yaml](config/settings.test.yaml)

不得新增 `configs/v3.yaml` 作为核心配置入口。

建议新增配置块：

```yaml
v3:
  enabled: false

model_router:
  enabled: false
  shadow_mode: true
  allow_low_risk_takeover: false

local_model:
  enabled: false
  provider: mock
  timeout_seconds: 3

lora:
  dataset_enabled: false
  inference_enabled: false
  registry_path: data/v3/model_registry.json

long_term_memory:
  write_enabled: false
  read_enabled: false
  ttl_days: 365

enhanced_safety:
  precheck_enabled: true
  final_guard_required: true
```

### 3.4 数据库策略

当前项目使用单文件 migration：

- [backend/app/db/migrations.py](backend/app/db/migrations.py)
- [backend/app/db/repositories.py](backend/app/db/repositories.py)

V3 不引入 Alembic。新增表必须使用 `CREATE TABLE IF NOT EXISTS`，并补充 repository 与集成测试。

---

## 4. RAG 与真实接入边界

V3 继续复用既有 RAG-SERVER：

```text
RAG-SERVER = 知识检索与事实来源
当前项目 = Agent 编排、多模型路由、安全、Memory、Eval、Trace
```

禁止：

- 新增第二套向量库。
- 新增第二套 embedding / chunking / BM25 / rerank 管线。
- 让 Agent / Verifier / 前端直接依赖 RAG-SERVER raw response。
- 把 Memory 当成第二套 RAG。
- 在真实 RAG 验收中静默降级到 fake。

允许：

- 默认单元测试使用 fake / mock。
- 默认回归使用 `-m "not rag_server"`。
- 涉及真实 RAG 的 smoke、real eval、citation 验收必须配置真实 RAG-SERVER。

---

## 5. 系统架构

```text
Frontend: backend/app/static/frontend
  |
  v
FastAPI: backend/app/main.py
  |
  +--> Existing V2 APIs: chat / measurement / rag / traces / eval
  |
  v
Multi-agent Graph: backend/app/agent/graph.py
  |
  +--> SupervisorAgent
  +--> RagAgent
  +--> DiseaseAgent
  +--> MeasurementAgent
  +--> VerifierAgent
  +--> SafetyAgent
  +--> ResponseAgent
  |
  v
V3 Additions
  |
  +--> FeatureFlagService
  +--> SafetyPrecheck
  +--> ModelRouter
  +--> LocalModelClient / LocalLoraModelClient
  +--> MemoryService
  +--> V3EvalRunner
  +--> Debug payload extension
  |
  v
Data Layer: SQLite
  |
  +--> existing V2 tables
  +--> model_route_log
  +--> safety_precheck_log
  +--> memory_event
  +--> farm_memory / animal_memory projections
  +--> v3_eval_run_log
  |
  v
External: existing RAG-SERVER through MCP stdio
```

---

## 6. V3-Core 分阶段计划

每个子任务约 1 小时可验收。每个子任务完成后必须：

```text
1. 运行该子任务指定测试。
2. 运行必要 V2 回归。
3. 不涉及真实 RAG 的任务运行 fake eval。
4. 涉及真实 RAG 的任务运行真实 RAG smoke/eval；缺配置时询问用户。
5. 使用简体中文 commit message 提交。
```

### V3.0：仓库实况映射与 V3 Harness

目标：把 GPT 版 spec 的错误路径全部替换为当前真实路径，并建立 V3 检查脚本。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.0-A1 | 生成项目实况映射 | `docs/V3_REPO_MAP.md` | 无 | 记录真实 APP_ROOT/TEST_ROOT/CONFIG_ROOT/RAG_SERVER_PATH | 人工检查 |
| V3.0-A2 | 新增 V3 检查脚本 | `scripts/check_v3.py`、`tests/integration/test_cli_scripts.py` | `check_v3.main` | 支持 `--stage 0/A/B/C/D/E/F/G/full`，默认不跑真实 RAG | `.venv\Scripts\python.exe scripts\check_v3.py --stage 0` |
| V3.0-A3 | 增加 V3 配置壳 | `backend/app/core/config.py`、`config/settings.yaml`、`config/settings.test.yaml`、`tests/unit/test_config.py` | `V3Settings` 等 | `v3.enabled=false` 时 V2 行为不变 | `.venv\Scripts\python.exe -m pytest tests\unit\test_config.py` |

### V3.1：Feature Flags 与回退护栏

目标：所有 V3 能力默认关闭，关闭时行为等价 V2。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.1-B1 | FeatureFlagService | `backend/app/services/feature_flag_service.py`、`tests/unit/test_feature_flags.py` | `FeatureFlagService` | 可读取 V3 / router / memory / lora flags | 单元测试 |
| V3.1-B2 | Debug payload 标记 V3 状态 | `backend/app/services/chat_service.py` 或 `backend/app/agent/response_agent.py` | `build_debug_payload` | V3 off 时仍保留 V2 输出 | API contract |
| V3.1-B3 | V2 等价回归 | `tests/e2e/test_v3_disabled_regression.py` | 无 | V3 off 时 chat/disease/measurement 与 V2 路径一致 | E2E |

### V3.2：SafetyPrecheck 与 Model Router Shadow

目标：SafetyPrecheck 在 Router 前执行；Router shadow 只记录决策，不改变实际模型调用。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.2-C1 | Safety taxonomy | `backend/app/safety/precheck.py` 或 `backend/app/agent/safety_precheck.py`、`tests/unit/test_safety_precheck.py` | `SafetyPrecheck.classify` | 覆盖 S0-S4、药物剂量、处方、群体发病、食品安全 | 单元测试 |
| V3.2-C2 | ModelRouter schema | `backend/app/model/router.py`、`tests/unit/test_model_router.py` | `ModelRouteRequest`、`ModelRouteDecision` | 输入输出稳定，禁止高风险走 local_small | 单元测试 |
| V3.2-C3 | Shadow route log | `backend/app/db/migrations.py`、`backend/app/db/repositories.py`、`tests/integration/test_model_route_log.py` | `ModelRouteLogRepository` | shadow 决策可写入 SQLite | 集成测试 |
| V3.2-C4 | 接入 graph shadow | `backend/app/agent/graph.py` | `record_shadow_route` | 不改变实际 answer，只增加 route trace | `test_agent_graph.py` |

### V3.3：低风险结构化任务路由接管

目标：只允许低风险结构化任务使用 local/mock model client；最终高风险回答不得交给 local_small。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.3-D1 | BaseModelClient | `backend/app/model/base.py`、`backend/app/model/local_client.py` | `BaseModelClient`、`LocalModelClient` | mock 输出固定 JSON | 单元测试 |
| V3.3-D2 | Query Normalize 试点 | `backend/app/model/query_normalizer.py` | `normalize_query` | 输出必须通过 schema 校验，失败回退 V2 | 单元/集成 |
| V3.3-D3 | Disease slot extraction 试点 | `backend/app/agent/disease_agent.py` | `extract_slots_with_router` | 只处理低风险槽位抽取；失败回退规则抽取 | 疾病 flow |
| V3.3-D4 | Measurement JSON 试点 | `backend/app/agent/measurement_agent.py` | `render_measurement_json` | 不改变体尺规则结论，只影响格式 | 体尺 E2E |

### V3.4：Verifier / Safety P0 增强

目标：强化 evidence support 与安全边界，不把 Verifier 包装成医学事实裁判。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.4-E1 | Claim schema | `backend/app/agent/verifier_agent.py`、`tests/unit/test_verifier_agent.py` | `ClaimCheck` | claim 必须关联 `source_uri` 或标记 unsupported | 单元测试 |
| V3.4-E2 | S4 硬拒绝规则 | `backend/app/agent/safety_agent.py`、`backend/app/rules/safety_rules.yaml` | `SafetyAgent.check` | 剂量/处方/确定诊断不可绕过 | safety tests |
| V3.4-E3 | red-team eval | `tests/fixtures/v3_safety_redteam.json`、`backend/app/evaluation/v3_safety_runner.py` | `V3SafetyEvalRunner` | 输出安全通过率 | eval test |

### V3.5：LoRA 数据治理 dry-run

目标：只做数据治理、脱敏、split、质量报告；不做真实训练 API。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.5-F1 | LoRA dataset schema | `backend/app/lora/dataset.py`、`tests/unit/test_lora_dataset.py` | `LoraTrainingExample` | 必填字段和禁止字段可校验 | 单元测试 |
| V3.5-F2 | 导出 dry-run | `scripts/export_lora_dataset.py`、`tests/integration/test_lora_export.py` | `export_lora_dataset` | 不含密钥、不过度导出 RAG 正文 | 集成测试 |
| V3.5-F3 | model registry 本地文件 | `backend/app/lora/registry.py` | `ModelRegistry` | JSON registry 可读写，默认不启用 inference | 单元测试 |

### V3.6：Memory MVP

目标：建立 append-only memory_event 和 farm/animal projection，不污染疾病判断。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.6-G1 | memory_event 表 | `backend/app/db/migrations.py`、`tests/integration/test_memory_schema.py` | migration | append-only 表存在，不更新原事件 | 集成测试 |
| V3.6-G2 | MemoryService | `backend/app/services/memory_service.py`、`tests/unit/test_memory_service.py` | `MemoryService` | 只写 user_confirmed/tool_result | 单元测试 |
| V3.6-G3 | animal/farm projection | `backend/app/db/repositories.py` | `MemoryRepository` | supersede/delete 生成新事件并更新 projection | 集成测试 |
| V3.6-G4 | 接入体尺和用户确认事实 | `backend/app/agent/graph.py`、`backend/app/api/measurement.py` | `maybe_write_memory` | 不把 AI 推断和诊断写入长期事实 | E2E |

### V3.7：V3 Eval 与最小 Debug 展示

目标：能比较 V2 baseline、V3 off、router shadow、router low-risk enabled。

| ID | 子任务 | 修改文件 | 类/函数 | 验收标准 | 测试 |
|---|---|---|---|---|---|
| V3.7-H1 | V3 eval runner | `backend/app/evaluation/v3_runner.py`、`scripts/run_eval.py` | `V3EvalRunner` | 新增 `--mode v3`，不破坏 fake/real/multi_agent | eval tests |
| V3.7-H2 | V3 report | `backend/app/evaluation/v3_report.py` | `build_v3_report` | 输出 JSON/Markdown，含 route/safety/memory/fallback | eval tests |
| V3.7-H3 | Debug payload/API | `backend/app/api/traces.py`、`backend/app/static/frontend/app.js` | `v3_debug_summary` | 前端展示 V3 flags、route、safety、memory 摘要 | frontend contract |
| V3.7-H4 | 真实 RAG 回归 | 不一定改代码 | 无 | 配置真实 RAG-SERVER 后 real eval 可运行，不静默 fake | `pytest -m rag_server` + real eval |

---

## 7. 测试方案

### 7.1 默认回归

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server"
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports\fake
.venv\Scripts\python.exe scripts\run_eval.py --mode multi_agent --output-dir reports\multi_agent
```

### 7.2 真实 RAG 验收

真实 RAG 验收不能用 fake 替代：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.venv\Scripts\python.exe -m pytest -m rag_server
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
```

如果此命令失败并提示缺少 API key、模型服务、知识库 collection 或 RAG-SERVER Python 环境，开发者必须停止并询问用户。

### 7.3 V3 stage check

V3 新增：

```powershell
.venv\Scripts\python.exe scripts\check_v3.py --stage 0
.venv\Scripts\python.exe scripts\check_v3.py --stage A
.venv\Scripts\python.exe scripts\check_v3.py --stage full
```

不新增 `check_v3.sh` 作为唯一入口。

---

## 8. Code Review 红线

- 不得重写 RAG-SERVER。
- 不得新增第二套 FastAPI app。
- 不得新增 `backend/tests` 或 `configs/` 作为主测试/主配置目录。
- 不得绕过 `SafetyAgent` / `FinalSafetyGuard`。
- 不得让 local_small 生成高风险最终回答。
- 不得把 LoRA 描述成知识注入或替代 RAG。
- 不得把 Memory 当作医学事实来源。
- 不得在真实 RAG 验收中静默降级到 fake。
- 不得提交 `.venv/`、`reports/`、`data/`、真实密钥。

---

## 9. 当前可进入开发的第一批任务

建议第一批只做：

```text
V3.0-A1：生成项目实况映射
V3.0-A2：新增 scripts/check_v3.py
V3.0-A3：增加 V3 配置壳
```

第一批不做 Model Router、不做 Memory、不做 LoRA 真实训练。完成第一批后再启动 code reviewer 审查 V3 接入点。

建议 commit 消息：

```text
V3.0-A1：生成 V3 项目实况映射并明确路径契约
V3.0-A2：新增 V3 阶段检查脚本并通过基线检查
V3.0-A3：新增 V3 配置开关并保持 V2 回归通过
```

---

## 10. 进度跟踪

| 阶段 | 目标 | 状态 | 主要验收命令 |
|---|---|---|---|
| V3.0 | 仓库实况映射与 V3 Harness | DONE（A1-A3 已完成） | `.venv\Scripts\python.exe scripts\check_v3.py --stage A` |
| V3.1 | Feature Flags 与回退护栏 | DONE（B1-B3 已完成） | `.venv\Scripts\python.exe -m pytest tests\unit\test_feature_flags.py tests\e2e\test_v3_disabled_regression.py` |
| V3.2 | SafetyPrecheck 与 Model Router Shadow | DONE（C1-C4 已完成） | `.venv\Scripts\python.exe -m pytest tests\unit\test_safety_precheck.py tests\unit\test_model_router.py tests\integration\test_model_route_log.py tests\integration\test_agent_graph.py` |
| V3.3 | 低风险结构化任务路由接管 | DONE（D1-D4 已完成） | `.venv\Scripts\python.exe -m pytest tests\unit\test_local_model_client.py tests\unit\test_query_normalizer.py tests\unit\test_disease_agent.py tests\unit\test_measurement_agent.py tests\e2e\test_measurement_report_flow.py` |
| V3.4 | Verifier / Safety P0 增强 | IN_PROGRESS（E1 已完成） | `.venv\Scripts\python.exe -m pytest tests\unit\test_verifier_agent.py` |
| V3.5 | LoRA 数据治理 dry-run | TODO | `.venv\Scripts\python.exe -m pytest tests\unit\test_lora_dataset.py` |
| V3.6 | Memory MVP | TODO | `.venv\Scripts\python.exe -m pytest tests\unit\test_memory_service.py` |
| V3.7 | V3 Eval 与最小 Debug 展示 | TODO | `.venv\Scripts\python.exe scripts\run_eval.py --mode v3` |
