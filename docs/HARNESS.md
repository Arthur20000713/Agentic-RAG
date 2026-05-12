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
py -3.11 -m pytest -m "not rag_server"
```

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
py -3.11 -m pytest tests/integration/test_rag_server_mcp_client.py tests/integration/test_rag_server_cli_gateway.py -m rag_server
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
