# V4.0 真实 RAG 稳定化开发记录

## 目标

V4.0 只修改当前 `Agentic RAG` 仓库；`RAG-SERVER` 仅允许只读诊断和本地运行验证，不修改其代码或配置。

核心目标是让真实 RAG 模式可预检、可运行、可归因，并且失败时不静默降级到 fake。

## 关键约束

- 不输出、不提交、不记录 API key 明文。
- `run_eval.py --mode real` 必须保持真实模式语义，失败只能 error 或 optional skipped，不能 fallback fake。
- 真实 RAG eval 默认使用 30s timeout；普通应用路径继续尊重配置。
- `RAG_TIMEOUT` 只允许重启 MCP 后重试 1 次；schema、mapping、tool error 不重试。
- source 信息不足时不伪造 citation，只记录 mapping warning。

## 进度跟踪

| 阶段 | 内容 | 状态 | 验证 |
|---|---|---|---|
| V4.0-A | 新增 RAG-SERVER 脱敏诊断与 real preflight，输出 `real_rag_preflight.json` | 已完成 | `python -m pytest tests/unit/test_rag_server_diagnostics.py tests/integration/test_real_rag_preflight.py tests/integration/test_eval_runner.py -k "real_rag or preflight or diagnostics"` |
| V4.0-B | `RAG_TIMEOUT` 重启 MCP 后重试 1 次，并在 `rag_trace_log` 记录 `attempt_count` | 已完成 | `python -m pytest tests/integration/test_rag_server_mcp_client.py tests/integration/test_rag_server_adapter.py tests/integration/test_rag_trace.py` |
| V4.0-C | citation/source_uri 归因增强，real eval 新增 coverage、mapping warning、error count | 已完成 | `python -m pytest tests/unit/test_rag_server_mapper.py tests/unit/test_eval_metrics.py tests/integration/test_eval_runner.py` |
| V4.0-D | 真实 RAG 只读验证与非 RAG 回归 | 已完成 | 见下方验证记录 |

## 当前结论

- Agentic RAG 默认 collection 仍为 `default`。
- RAG-SERVER 配置诊断会读取 `config/settings.yaml` 并只输出 provider、model、collection、路径和 key 是否存在。
- 如果 RAG-SERVER `vector_store.collection_name` 与 Agentic RAG `rag_server.collection` 不一致，会输出 `RAG_COLLECTION_MISMATCH` warning。
- real eval optional 失败会同时写 `eval_result.*`、`eval_summary.md`、`failure_analysis.md` 和 `real_rag_preflight.json`。

## 验证记录

| 命令 | 结果 | 备注 |
|---|---|---|
| `$env:RAG_SERVER_PATH='C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER'; .venv\Scripts\python.exe -m pytest -m rag_server -q` | 通过，`3 passed, 259 deselected` | 只读 smoke，确认 MCP tools/list 和 list_collections 可调用。 |
| `$env:RAG_SERVER_PATH='C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER'; .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir .tmp_tests\real_eval_v4` | skipped，退出码 0 | `real_rag_preflight.json` 报告 `RAG_COLLECTION_NOT_FOUND`，target collection 为 `default`；诊断显示 RAG-SERVER 配置 collection 为 `knowledge_hub`，warning 为 `RAG_COLLECTION_MISMATCH`。 |
| `.venv\Scripts\python.exe scripts\run_eval.py --mode v3 --output-dir .tmp_tests\v3_eval_v4` | 通过，退出码 0 | V3 eval 回归通过。 |
| `.venv\Scripts\python.exe -m pytest -m "not rag_server" -q` | 通过，`259 passed, 3 deselected` | 默认非真实 RAG 回归通过。 |

## 后续建议

真实 RAG 当前被 preflight 阻断的主要原因不是 fake fallback，而是 collection 对齐问题：Agentic RAG 目标 collection 是 `default`，RAG-SERVER 配置 collection 是 `knowledge_hub`，且 `list_collections` 当前未返回 `default`。下一步应由人工确认是否把 Agentic RAG `rag_server.collection` 调整为 `knowledge_hub`，或先在 RAG-SERVER 中完成目标 collection 的真实入库。
## V4.0-E 真实端到端稳定化补充

- 状态：已完成。
- 只修改 Agentic RAG，不修改 RAG-SERVER 代码或配置。
- 新增 RAG-SERVER Markdown 集合列表解析，支持 `## Available Collections` / `1. **default**` 格式。
- 新增 RAG-SERVER `References (JSON)` fenced JSON 解析，把真实 MCP 返回映射为标准 hits/citations/source_uri。
- 当原始 RAG-SERVER 目录在当前运行环境触发 Chroma `readonly database` 或日志 `Permission denied` 时，Agentic RAG 会在 `.tmp_tests/rag_server_runtime/<hash>` 准备可写运行时副本，并从副本启动 MCP stdio；不会回退到 fake。
- 验证结果：真实 RAG 预检通过，`default` collection 可发现；单次真实 query 成功返回 1 个 hit 和 1 个 citation；完整 real eval 稳定跑完，无 timeout、无 RAG error、rag citation/source_uri coverage 均为 100%。
- 已知剩余质量问题：当前 RAG-SERVER 真实库只有 `simple.pdf` 样本文档，local-hash embedding 会对 `no_answer` 类问题也召回该样本文档，所以 real eval 为 55/60，通过率 91.67%，5 个失败均为 no_answer 质量问题，不是链路不可用问题。
