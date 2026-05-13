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
.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
```

说明：当前通用 golden set 主要用于 V1/fake regression；`multi_agent` 模式会计算 route/path/safety/trace 指标，默认 golden set 中部分英文泛化样本会暴露路由质量差异，这是评测结果，不代表脚本不可用。

## 文档入口

- `DEV_SPEC.md`：V2 开发阶段、约束和进度跟踪。
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
