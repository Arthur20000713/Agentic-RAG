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
