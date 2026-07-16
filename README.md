# 畜牧业 Agentic RAG 智能助手

这是一个面向畜牧业问答、疾病问诊辅助、体尺报告和真实知识库检索的 FastAPI 应用层项目。项目不重写底层 RAG，而是接入 sibling 项目 `RAG-SERVER` 作为知识检索核心，通过 MCP stdio 调用真实知识库，并在本仓库内提供 API、多 Agent 工作流、运行时诊断、前端演示、评测与发布验收入口。

## 当前状态

V6 产品化收口已完成，本机验收结论为 `usable`。

当前默认配置：

- 真实 RAG 默认开启：`rag_server.query_mode=real`
- 默认知识库 collection：`livestock_v4_2`
- V3 agent graph 默认开启
- ModelRouter 默认 `shadow_mode=false`，允许低风险结构化任务由本地模型接管
- 本地模型默认使用 `transformers`
- 本地模型型号：`Qwen/Qwen2.5-0.5B-Instruct`
- 本地模型只验收 `query_normalization`，不生成最终答案
- LoRA adapter 默认不启用

最新发布验收命令：

```powershell
.venv\Scripts\python.exe scripts\check_release_v6.py --output-dir .tmp_tests\v6_release
```

期望输出包含：

```text
V6 release status: usable
```

最近一次本机验收结果：

- `runtime_doctor`: passed
- `v6_full_check`: passed
- `local_model_smoke`: passed
- `pytest_not_rag_server`: passed
- 回归测试：`457 passed, 3 deselected`

## 主要能力

- 畜牧业知识问答：基于真实 RAG 检索结果生成自然语言答案，并保留 citation/source_uri。
- 疾病问诊辅助：抽取物种、症状、持续时间、体温、群体发病等槽位；信息不足时追问；高风险内容走安全拦截。
- 疾病 LLM 灰度链路：支持病例结构化理解、会话补充合并、RAG 查询构造、证据门、条目级引用推理和 verifier 安全校验；默认关闭，不静默 fake。
- 体尺报告：分析当前体尺和历史记录，输出结构化摘要、异常项、证据和建议。
- 真实 RAG 集成：通过 MCP stdio 调用 `RAG-SERVER`，默认走真实 collection `livestock_v4_2`，不静默降级到 fake。
- 多 Agent 工作流：包含 Supervisor、RAG、Disease、Measurement、Verifier、Safety、Response 等节点，并记录 agent path。
- 运行时诊断：提供 doctor、health、readiness、RAG status、本地模型验收状态。
- 本地模型路径：Transformers 模型已通过 RTX 3060 Laptop GPU 的 query normalization smoke。
- 静态前端：访问 `/app` 可演示 Chat、Measurement 和 Debug JSON Panel。

## 快速启动

在项目根目录运行：

```powershell
.\scripts\start_app.ps1 -Port 8001
```

打开：

```text
http://127.0.0.1:8001/app
http://127.0.0.1:8001/docs
```

启动脚本会先运行 V6 runtime doctor。若 doctor 失败，应先按错误码修复配置或环境。

## 运行时诊断

```powershell
.venv\Scripts\python.exe scripts\doctor_v6.py --json
```

关键检查项：

- `default_real_rag`
- `rag_server_path`
- `rag_server_python`
- `quality_gate`
- `v3_agent_path`
- `disease_llm_path`
- `local_model_acceptance`

HTTP 诊断接口：

```text
GET /api/health
GET /api/ready
GET /api/rag/status
GET /api/rag/collections
```

`/api/health` 只表示应用存活；`/api/ready` 会汇总真实 RAG、质量门禁、V3 agent path 和本地模型验收状态。

## 真实 RAG-SERVER

默认配置指向本机 sibling 项目：

```yaml
rag_server:
  query_mode: real
  repo_path: C:/Users/DELL/PycharmProjects/PythonProject/RAG-SERVER
  python_executable: C:/Users/DELL/PycharmProjects/PythonProject/RAG-SERVER/.venv/Scripts/python.exe
  collection: livestock_v4_2
  timeout_seconds: 30
  strict_real_mode: true
```

可用环境变量覆盖 RAG-SERVER 路径：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
```

真实 RAG 验证：

```powershell
.venv\Scripts\python.exe -m pytest -m rag_server
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
```

`--optional` 只允许未配置环境时生成 skipped report；不会把 real 静默降级为 fake。

## 本地 Transformers 模型

默认本地模型配置：

```yaml
local_model:
  enabled: true
  provider: transformers
  model: Qwen/Qwen2.5-0.5B-Instruct
  timeout_seconds: 60
  max_retries: 1
  allow_final_answer: false
  device: auto
  torch_dtype: auto
  max_new_tokens: 96
  temperature: 0
```

本地模型验收命令：

```powershell
.venv\Scripts\python.exe scripts\run_local_model_smoke.py --optional --output reports\local_model_v6_transformers_smoke.json
```

V6.5 验收要求该命令返回：

```text
PASSED: local model smoke provider=transformers
```

`skipped` 不能作为 V6.5 的通过证据。

本地模型安全边界：

- 仅验收 `query_normalization`
- `model_router.shadow_mode=false`
- `model_router.allow_low_risk_takeover=true`
- `local_model.allow_final_answer=false`

## 常用检查命令

```powershell
.venv\Scripts\python.exe scripts\check_v6.py --stage full
.venv\Scripts\python.exe scripts\check_release_v6.py --output-dir .tmp_tests\v6_release
.venv\Scripts\python.exe -m pytest -m "not rag_server" -q
.venv\Scripts\python.exe scripts\run_local_model_smoke.py --optional --output reports\local_model_v6_transformers_smoke.json
```

V4.2 真实知识库批次检查：

```powershell
.venv\Scripts\python.exe scripts\check_v4_2.py --stage full
.venv\Scripts\python.exe scripts\check_rag_corpus.py --batch docs\rag_corpus\batches\batch_002.yaml --dry-run
.\scripts\check_real_batch.ps1 -Batch docs\rag_corpus\batches\batch_002.yaml -OutputDir reports\real_v4_2_batch
```

## API 入口

主要接口：

- `POST /api/chat`
- `POST /api/measurement/analyze`
- `POST /api/documents/upload`
- `POST /api/tasks/{task_id}/index`
- `GET /api/tasks/{task_id}`
- `GET /api/traces/{request_id}`
- `GET /api/rag/status`
- `GET /api/rag/collections`

统一响应结构：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "req_xxx"
}
```

## 文档入口

- [`docs/LANGGRAPH_MIGRATION.md`](docs/LANGGRAPH_MIGRATION.md)：LangGraph 工作流拓扑、迁移边界、测试与回滚策略。
- `docs/DEV_SPEC_V6.md`：V6 产品化收口开发规范和进度表。
- `docs/V6_RELEASE_CHECKLIST.md`：V6 发布验收清单。
- `docs/V6_LOCAL_MODEL_ACCEPTANCE.md`：本地 Transformers 模型验收说明。
- `docs/V5_LOCAL_MODEL_GUIDE.md`：本地模型接入说明。
- `docs/V4_2_KNOWLEDGE_BASE_GUIDE.md`：真实知识库批次、入库和质量门禁指南。
- `docs/API_SPEC.md`：FastAPI contract。
- `docs/MCP_SPEC.md`：应用层 MCP tool contract。
- `docs/RAG_SERVER_INTEGRATION.md`：真实 RAG-SERVER 接入规则。
- `docs/SAFETY_SPEC.md`：安全边界。
- `docs/EVAL_SPEC.md`：评测集合、指标和输出。
- `docs/DEMO_SCRIPT.md`：演示脚本。

## 安全边界

系统只提供畜牧业辅助建议，不替代兽医诊断，不输出具体药物剂量，不给确定性处方，不绕过停药期、食品安全或监管要求。所有最终输出必须经过 Safety Agent 或 Final Safety Guard。

高风险请求会被拦截或引导用户联系执业兽医。真实 RAG 引用只能作为资料依据，不等同于人工诊断结论。

## 当前未覆盖范围

V6 达到本机产品级验收，但仍不是公网生产部署：

- 未实现多用户权限和租户隔离。
- 未实现生产级备份/恢复和告警。
- 未启用真实 LoRA adapter 推理。
- 未提供企业级审计、访问控制和运维面板。
