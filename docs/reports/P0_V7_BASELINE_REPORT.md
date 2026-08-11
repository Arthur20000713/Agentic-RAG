# V7 P0 基线与容器风险报告

日期：2026-07-29

分支：`codex/java-enterprise-integration`
基线提交：`08df5e1`

## 结论

当前 Agentic RAG 主仓库的非真实 RAG 回归、V6 release、本地模型 smoke、fake eval 和现有浏览器主流程均通过，可以在保持旧 `/api` 兼容的前提下继续开发 `/internal/v1`。

RAG-SERVER 的同进程镜像方案只完成了本机协议和依赖可行性验证，尚未达到“干净 clone 可复现”的容器交付门槛。P1 可以使用 fake RAG 和受控 MCP stub 独立推进，但在外部依赖完成安全清理和固定版本前，不得宣称真实 RAG Compose 已交付。

## 已通过门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 非真实 RAG 全量回归 | `526 passed, 3 deselected` | `.tmp_tests/p0_v7_release_final/pytest_not_rag_server.log` |
| V6 full check | passed | `.tmp_tests/p0_v7_release_final/v6_full_check.log` |
| V6 release | `usable` | `.tmp_tests/p0_v7_release_final/release_check_summary.json` |
| Transformers smoke | passed | `.tmp_tests/p0_v7_release_final/local_model_smoke.json` |
| fake eval | `60/60`, pass rate `1.0` | `.tmp_tests/p0_fake_eval/eval_summary.md` |
| OpenAPI 草案 | 9 paths、37 schemas，Redocly 0 warning / 0 error | `contracts/ai-service-v1.yaml` |
| 外部 Chrome 手工验收 | 页面加载、模式切换、实际体尺分析和控制台检查通过 | 本阶段验收记录 |
| `git diff --check` | passed | 本阶段命令记录 |

第一次 release 中本地模型进程曾以 Windows `0xC0000005` 退出且没有测试断言或错误日志。相同 smoke 隔离重跑通过，随后完整 release 再次运行也通过，因此记录为一次不可复现的原生进程异常，不通过降低门禁或跳过 smoke 处理。

## 已固定的服务边界

- Java 是唯一外部业务入口，也是用户、权限、会话、消息、任务、审计和业务数据的事实源。
- Python 保留 RAG、Agent、问诊编排、模型调用、技术 trace 和评测。
- Java 通过内部 HTTP 调用 Python；同步 chat 默认不自动重试，响应不确定时按 operation ID 对账。
- MySQL 保存 Java 业务数据；Redis 保存认证撤销、幂等、限流和 opaque AI context cache。
- `conversation.context_version` 是上下文版本权威；Python 接收有界历史和 opaque context，并返回 `nextContext`。
- 第一种可靠异步任务仅实现 `DOCUMENT_INDEX`。

详细决策见：

- `docs/adr/0001-java-python-service-boundary.md`
- `docs/adr/0002-idempotency-reconciliation-and-context.md`
- `docs/adr/0003-rag-server-containerization.md`

## RAG-SERVER 与容器阻断

以下问题不属于本仓库 P1 契约实现可安全修复的范围：

1. 当前 MCP 客户端会命中 `.tmp_tests/rag_server_runtime/...` 的陈旧副本；`livestock_v4_2` 只存在于该副本，sibling RAG-SERVER 当前工作树没有该集合。
2. sibling RAG-SERVER 的受版本管理配置含内联凭证。未读取或复制凭证值；相关凭证必须轮换，并在该仓库形成无密钥的新提交。
3. sibling RAG-SERVER 工作树包含 staged、unstaged 和 untracked 改动，不能由本任务擅自修改、提交或打包。
4. `batch_002.yaml` 仍引用宿主机 `C:\tmp` 语料，缺少可合法分发、带 checksum 和 provenance 的索引制品或完整重建输入。
5. 两个 Python 项目尚无统一 hash lock；正式镜像必须在干净环境生成锁文件并通过 `pip check`。
6. Docker 拉取基础镜像受到当前镜像源 401 / APT 502 影响，干净 Linux 镜像的完整依赖安装证据尚未形成。
7. sibling RAG 配置依赖 Ollama embedding；容器中 `localhost:11434` 不成立，必须固定外部服务边界和模型 digest。

## 本仓库后续可控修复

P1 同时处理以下问题：

- 正常 MCP 启动不再优先使用历史 runtime copy；runtime copy 只作为只读失败后的即时、重建式 fallback。
- FastAPI lifespan 在关闭时回收 MCP 子进程。
- 持续消费 MCP stderr，避免长时间运行时管道写满。
- 新 `/internal/v1/health/readiness` 使用真实 HTTP 200/503，并在 real RAG 模式检查 MCP handshake、工具列表和目标 collection。
- 内部接口使用服务 Bearer token、真实 4xx/5xx、request ID 和幂等执行记录。

## 关闭 P0 外部门禁所需条件

真实 RAG Compose 交付前仍需：

1. 轮换已暴露凭证并生成安全、远端可达的 RAG-SERVER commit/tag；
2. 以 submodule 或等价不可变制品固定版本；
3. 提供可重建知识库输入，或提供许可与 checksum 完整的脱敏索引种子；
4. 在干净 Linux 构建中通过依赖安装、`pip check`、MCP handshake 和 collection 查询；
5. 通过 Compose health、重启持久化和真实 RAG E2E。

这些条件未完成前，自动化报告必须把 fake、stub、陈旧本机索引和真实可复现 RAG 明确区分。
