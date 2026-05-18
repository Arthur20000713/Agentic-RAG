# 开发护栏

本项目采用本地优先的测试护栏：

- 默认测试使用 fake RAG client。
- 真实 RAG-SERVER 测试必须标记为 `rag_server`，且未设置 `RAG_SERVER_PATH` 时跳过。
- 修改 API schema 后同步 `docs/API_SPEC.md` 并运行 API 契约测试。
- 修改 MCP tool schema 后同步 `docs/MCP_SPEC.md` 并运行 MCP 契约测试。
- 修改 Safety 规则后同步 `docs/SAFETY_SPEC.md` 并运行安全测试。
- 不复制 RAG-SERVER 的真实配置或密钥。

本轮可用检查：

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server"
```

V4.1 阶段检查：

```powershell
.venv\Scripts\python.exe scripts\check_v4_1.py --stage baseline
.venv\Scripts\python.exe scripts\check_v4_1.py --stage corpus
.venv\Scripts\python.exe scripts\check_v4_1.py --stage full
.venv\Scripts\python.exe scripts\check_v4_1.py --stage full --real-rag --real-rag-output-dir .tmp_tests\v4_1_real_rag_smoke
```

`--stage full` 默认只跑本仓库只读检查，不启动真实 RAG。只有显式传入 `--real-rag` 才会运行 `pytest -m rag_server` 和 real eval optional。

V4.1 语料入库 dry-run：

```powershell
.venv\Scripts\python.exe scripts\check_rag_corpus.py --manifest docs\rag_corpus\source_manifest.yaml --dry-run
```

该命令只输出计划，不写 RAG-SERVER，不读取或打印 API key。

V4.2 批次化真实 RAG 回归：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.\scripts\check_real_batch.ps1 -Batch docs\rag_corpus\batches\batch_002.yaml -OutputDir reports\real_v4_2_batch
```

该脚本只编排本项目命令：`check_v4_2 --stage full`、`pytest -m rag_server`、`run_eval.py --mode real --optional --batch ...` 和 `check_v4_2 --stage gate ...`。它要求显式传入 batch 与 output-dir；缺少 `RAG_SERVER_PATH` 时直接退出，不会切换到 fake，也不会打印密钥。

V4.2 batch dry-run：

```powershell
.venv\Scripts\python.exe scripts\check_rag_corpus.py --batch docs\rag_corpus\batches\batch_002.yaml --dry-run
```

该命令只输出计划入库命令，包含 collection、文件路径和 source_id，不执行 RAG-SERVER 入库。

阶段 D 局部检查：

```powershell
py -3.11 -m pytest tests/integration/test_mcp_tools.py tests/integration/test_tool_timeout.py tests/unit/test_template_client.py tests/unit/test_answer_generator.py
```

阶段 E 局部检查：

```powershell
py -3.11 -m pytest tests/unit/test_disease_risk.py tests/unit/test_measurement_analyzer.py tests/unit/test_safety.py tests/integration/test_mcp_tools.py
```

C7/C8 局部检查：

```powershell
py -3.11 -m pytest tests/integration/test_rag_server_mcp_client.py -m "not rag_server"
```

阶段 F 局部检查：

```powershell
py -3.11 -m pytest tests/unit/test_agent_router.py tests/unit/test_slot_extractor.py tests/unit/test_verifier.py tests/integration/test_agent_workflow.py tests/e2e/test_disease_consultation_flow.py tests/e2e/test_measurement_report_flow.py
```

阶段 G 局部检查：

```powershell
py -3.11 -m pytest tests/integration/test_api_contract.py tests/integration/test_cli_scripts.py
```

Phase H local E2E check:

```powershell
py -3.11 -m pytest tests/e2e/test_document_qa_flow.py tests/e2e/test_disease_consultation_flow.py tests/e2e/test_measurement_report_flow.py -m "not rag_server"
```

Optional real RAG-SERVER smoke tests:

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
# Optional if auto-detection from scripts\run_local.ps1 does not match your RAG-SERVER runtime:
# $env:RAG_SERVER_PYTHON="C:\Users\DELL\.conda\envs\all-in-rag\python.exe"
py -3.11 -m pytest -m rag_server
```

Phase I evaluation check:

```powershell
py -3.11 -m pytest tests/unit/test_golden_set_schema.py tests/unit/test_eval_metrics.py tests/integration/test_eval_runner.py
py -3.11 scripts/run_eval.py
```

V2.1-A5 RAG trace persistence check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_rag_trace.py tests/integration/test_sqlite_schema.py
```

V2.1-A6 RAG trace integration check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_rag_server_adapter.py tests/integration/test_rag_server_mcp_client.py -m "not rag_server"
```

V2.1-A7 RAG collections API check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_rag_api.py -k collections
```

V2.1-A8 RAG document summary API check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_rag_api.py -k summary
```

V2.1-A9 RAG timeout/fallback check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_rag_server_adapter.py -k timeout
```

V2.1-A10 real RAG-SERVER smoke check:

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.venv\Scripts\python.exe -m pytest -m rag_server
```

V2.1-A11 real RAG eval runner check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py -k real_rag
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional
```

V2.1-A12 failure category check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_eval_metrics.py -k failure
```

V2.2-B1 multi-agent state check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_multi_agent_state.py
```

V2.2-B2 agent trace persistence/API check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_trace_api.py -k agent
```

V2.2-B3 supervisor agent route check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_supervisor_agent.py tests/unit/test_agent_router.py
```

V2.2-B4 RAG agent evidence status check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_rag_agent.py
```

V2.2-B5 disease agent follow-up/risk check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_disease_agent.py
```

V2.2-B6 measurement agent report check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_measurement_agent.py
```

V2.2-B7 verifier agent evidence check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_verifier_agent.py
```

V2.2-B8 safety agent blocking check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_safety_agent.py
```

V2.2-B9 response agent output check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_response_agent.py
```

V2.2-B10 general QA graph check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_agent_graph.py -k general
```

V2.2-B11 disease graph check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_agent_graph.py -k disease
```

V2.2-B12 measurement graph check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_agent_graph.py -k measurement
```

V2.3-C1 static frontend contract check:

```powershell
.venv\Scripts\python.exe scripts\check_v2.py --frontend-contract
```

V2.3-C2 chat frontend contract check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py -k chat
```

V2.3-C3 frontend sources/tools contract check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py -k sources
```

V2.3-C4 measurement frontend contract check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py -k measurement
```

V2.3-C5 debug panel frontend contract check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_frontend_contract.py -k debug
```

V2.3-C6 frontend smoke check:

```powershell
.venv\Scripts\python.exe -m pytest tests/e2e/test_frontend_smoke.py
```

V2.4-D1 session context schema check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_session_context_schema.py -k schema
```

V2.4-D2 session context service check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_session_context.py -k service
```

V2.4-D3 session context slot sources check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_session_context.py -k slot_sources
```

V2.4-D4 session context TTL check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_session_context.py -k ttl
```

V2.4-D5 session follow-up flow check:

```powershell
.venv\Scripts\python.exe -m pytest tests/e2e/test_session_follow_up_flow.py
```

V2.4-D6 session reset check:

```powershell
.venv\Scripts\python.exe -m pytest tests/e2e/test_session_follow_up_flow.py -k reset
```

V2.5-E1 eval run log check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py -k log
```

V2.5-E2 real RAG failure analysis check:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_eval_metrics.py -k failure
.venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py -k real_rag
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional
```

V2.5-E3 multi-agent eval metrics check:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_eval_runner.py -k multi_agent
```

V2.5-E4 V2 docs contract check:

```powershell
.venv\Scripts\python.exe scripts\check_v2.py --docs
```

V2.5-E5 demo script review check:

```powershell
.venv\Scripts\python.exe scripts\check_v2.py --docs
```
