# 畜牧业 Agentic RAG 智能助手

这是一个面向畜牧业问答、疾病问诊辅助和体尺报告生成的 FastAPI 应用层项目。V2 不重写底层 RAG，而是把已有 sibling 项目 `RAG-SERVER` 作为知识检索核心，通过 MCP stdio 接入，并在本项目内完成 API、Multi-agent workflow、trace、session context、前端演示页和评测闭环。

## 当前能力

- Chat 问答：支持畜牧业知识问答、引用展示、无证据保守拒答。
- 疾病问诊：抽取物种、症状、持续时间、体温、群体发病等槽位；信息不足时追问；高风险内容经过安全拦截。
- 体尺报告：分析当前体尺和历史记录，输出结构化摘要、异常项、证据和建议。
- RAG-SERVER 接入：支持 `fake`、`smoke`、`real` 三种模式，真实模式通过 `python -m src.mcp_server.server` 调用 sibling RAG 项目。
- Multi-agent workflow：包含 Supervisor、RAG、Disease、Measurement、Verifier、Safety、Response 等节点，并记录 agent path。
- Trace 和评测：支持 `rag_trace_log`、`agent_trace_log`、`eval_run_log`，可生成 fake eval、real RAG optional eval、multi-agent eval 和失败分析报告。
- 静态前端：访问 `/app` 可演示 Chat、Measurement 和 Debug JSON Panel。

## 当前阶段边界

当前开发基线位于 V4.2。真实 RAG-SERVER MCP 链路、preflight、timeout retry、citation/source_uri 映射和 real eval 报告已经完成；V4.2 的重点是把真实知识库扩展工程化为 source manifest、corpus batch、batch dry-run、real eval 和 quality gate 的闭环。

- `v3.enabled` 默认关闭，`/api/chat` 默认仍走 V2 workflow。
- `local_model.provider="mock"` 是结构化 mock，不是真实本地大模型推理。
- LoRA 当前是数据治理和导出 dry-run，不包含真实训练或推理启用。
- 当前真实 RAG 的主要质量问题是知识库样本偏弱和 no-answer/弱相关召回，不是链路不可用。
- V4.2 已新增版本化资料源 manifest、`batch_002` 批次计划、V4.2 真实评测集、质量门禁、报告 diff、批次回归脚本和前端 Debug RAG 状态展示。

## 快速运行

安装依赖后使用项目根目录下的 `.venv`：

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server"
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/app
http://127.0.0.1:8000/docs
```

## 真实 RAG-SERVER

真实 RAG 不是默认检查项，必须显式配置：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
# 如 RAG-SERVER 需要独立 Python，可选：
# $env:RAG_SERVER_PYTHON="C:\path\to\python.exe"
.venv\Scripts\python.exe -m pytest -m rag_server
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
```

未配置真实 RAG 时，`--mode real --optional` 会输出 skipped report 和 `failure_analysis.md`，不会静默降级到 fake。

## 评测命令

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports\fake
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
.venv\Scripts\python.exe scripts\run_eval.py --mode multi_agent --golden-set tests\fixtures\golden_set.json --output-dir reports\multi_agent
.venv\Scripts\python.exe scripts\check_v4_1.py --stage full
.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
```

说明：当前通用 golden set 主要用于 V1/fake regression；`multi_agent` 模式会计算 route/path/safety/trace 指标，默认 golden set 中部分英文泛化样本会暴露路由质量差异，这是评测结果，不代表脚本不可用。

V4.1 真实评测集位于 `tests/fixtures/real_golden_v4_1/`，按 `answerable`、`no_answer`、`safety` 分组。真实入库资料源由 `docs/rag_corpus/source_manifest.yaml` 管理，执行 RAG-SERVER 入库前必须由用户确认资料文件和 collection。

V4.2 真实知识库资产：

- 当前 manifest：`docs/rag_corpus/source_manifest.yaml`
- 版本化 manifest：`docs/rag_corpus/manifests/livestock_v4_2.yaml`
- 批次计划：`docs/rag_corpus/batches/batch_002.yaml`
- 批次质量报告模板：`docs/rag_corpus/reports/batch_002_quality.md`
- 真实评测集：`tests/fixtures/real_golden_v4_2/all.json`

标准 V4.2 验收命令：

```powershell
.venv\Scripts\python.exe scripts\check_v4_2.py --stage full
.venv\Scripts\python.exe scripts\check_rag_corpus.py --batch docs\rag_corpus\batches\batch_002.yaml --dry-run
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.\scripts\check_real_batch.ps1 -Batch docs\rag_corpus\batches\batch_002.yaml -OutputDir reports\real_v4_2_batch
```

`livestock_v4_2` collection 必须由用户确认资料文件和 RAG-SERVER 环境后入库。若 collection 不存在，real eval 会写 skipped report，不能作为通过质量门禁的证据。

## 文档入口

- `DEV_SPEC.md`：V2 开发阶段、约束和进度跟踪。
- `DEV_SPEC_v4_1.md`：V4.1 真实知识库质量闭环开发计划。
- `DEV_SPEC_v4_2.md`：V4.2-V4.5 剩余 V4 阶段开发计划。
- `docs/V4_1_BASELINE.md`：V4.1 当前开发基线和能力边界。
- `docs/V4_2_KNOWLEDGE_BASE_GUIDE.md`：V4.2 知识库批次、入库和质量门禁指南。
- `docs/API_SPEC.md`：FastAPI contract。
- `docs/MCP_SPEC.md`：应用层 MCP tool contract。
- `docs/RAG_SERVER_INTEGRATION.md`：真实 RAG-SERVER 接入规则。
- `docs/SAFETY_SPEC.md`：安全边界。
- `docs/EVAL_SPEC.md`：评测集合、指标和输出。
- `docs/HARNESS.md`：开发和验收命令。
- `docs/INTERVIEW_NOTES.md`：面试讲解提纲。
- `docs/DEMO_SCRIPT.md`：演示脚本。

## 安全边界

系统只提供畜牧业辅助建议，不替代兽医诊断，不输出具体药物剂量，不给确定性处方。所有最终输出必须经过 Safety Agent 或 Final Safety Guard。
