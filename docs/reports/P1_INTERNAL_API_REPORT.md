# P1 Internal AI API 阶段报告

日期：2026-07-29

分支：`codex/java-enterprise-integration`

## 1. 阶段结论

P1 已完成仓库内可控范围：FastAPI 提供与
`contracts/ai-service-v1.yaml` 对齐的 `/internal/v1` 服务间 API，支持服务认证、
request ID、幂等执行、operation 对账、无状态上下文、独立健康探针和安全错误语义。

P1 不代表真实 RAG Compose 已可复现。真实 RAG 仍受
`docs/reports/P0_V7_BASELINE_REPORT.md` 中固定版本、密钥轮换、语料路径和
`livestock_v4_2` 集合缺失等外部条件阻断。

## 2. 已实现范围

- 9 个 `/internal/v1` operation 与 committed OpenAPI path 对齐；
- 服务 Bearer token 使用 `SecretStr` 和常量时间比较；
- `X-Request-ID` 校验、响应回显和统一错误响应；
- `operationId` + `Idempotency-Key` 全局绑定、请求 canonical SHA-256、结果重放和冲突检测；
- 独立 SQLite connection 保存 `ai_execution_record`，不提交旧业务 connection；
- execution 终态条件更新、过期清理、失败 HTTP 状态重放和 operation 查询；
- Java 输入有界 history 与 opaque context，Python 返回 `nextContext` 和递增版本；
- internal chat 不写旧 `conversation`、`qa_log` 或 `session_context`；
- 正常回答、动态追问、低置信度和安全拒答映射；
- 低置信度、空结果和安全拒答强制不返回 citation；
- measurement 只使用请求携带的 history；
- liveness 与 readiness 分离，readiness 使用真实 200/503；
- MCP stderr 持续 drain，初始化失败、运行中传输失败和应用 shutdown 均回收子进程；
- execution 终态写库失败映射为可机器处理的 503，而不是泄漏默认 500；
- `deadlineMs` 与 OpenAPI 一致为必填字段；
- Bearer scheme 按标准大小写不敏感。

## 3. 明确边界

`POST /internal/v1/ai/knowledge/ingestions` 在 P1 只创建持久化 `ACCEPTED`
execution stub，并返回 `Location`。它没有执行文件 hash/object 校验、可靠 worker、
重试、索引或最终业务状态更新；这些属于 P6。

“不保存问诊正文”只适用于 `ai_execution_record` 的 canonical request hash。
Python 按既定架构继续保留 Agent/RAG 技术 trace，当前 trace 可包含原始 query；
后续应通过保留期、访问控制和脱敏策略管理，不能把该结论扩大为全系统不保存正文。

## 4. 自动化验证

P1 最终审查修复后的结果：

- 定向 internal API、execution store 与 MCP 回归：
  `47 passed, 1 skipped`；
- 全量非真实 RAG 回归：
  `565 passed, 3 deselected`；
- fake golden evaluation：
  `60/60`，所有指标 `100%`；
- V6 release harness：
  `usable`，包含 runtime doctor、full check、本地 Transformers smoke 和
  `565 passed, 3 deselected`；
- `python -m compileall backend tests`：通过；
- `git diff --check`：通过，仅有仓库既有 LF/CRLF 转换提示；
- Ruff：当前虚拟环境未安装，未宣称通过。

证据：

- `.tmp_tests/p1_post_audit_fake_eval/eval_summary.md`
- `.tmp_tests/p1_post_audit_v6_release/release_check_summary.json`

## 5. 外部 Chrome 手工验收

已通过真实外部 Chrome 访问运行中的 FastAPI：

- liveness：HTTP 200，`UP`；
- readiness：HTTP 200，`READY`；
- grounded chat：`ANSWERED`、`SUPPORTED`、两条真实映射 citation、
  `contextVersion=1`、真实 `agent_trace_1`；
- low-confidence：`LOW_CONFIDENCE` 且 `sources=[]`；
- operation reconciliation：相同 operation/run/result，状态 `SUCCEEDED`；
- 页面控制台无应用错误。

验收临时 HTML 和 P1 测试服务均已清理。
