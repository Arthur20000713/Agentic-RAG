# P7.1 稳定性与可观测性阶段报告

日期：2026-08-10

分支：`codex/java-enterprise-integration`

状态：完成

## 1. 已实现范围

- Java 引入 Micrometer Prometheus registry，暴露受 RBAC 保护的
  `/actuator/prometheus`。
- Prometheus 使用固定低基数标签记录 AI 调用次数和耗时：
  `livestock.ai.calls`、`livestock.ai.duration`，覆盖聊天、聊天对账、
  体尺分析、文档索引提交和索引对账。
- Actuator readiness 聚合 MySQL、Redis 和 Python AI；liveness 保持只反映
  Java 进程自身状态。
- Java 控制台日志使用 Logstash JSON，并通过 MDC 关联 request ID。
- MySQL Hikari 获取连接超时收紧为 5 秒、校验超时为 2 秒，避免依赖故障时
  默认约 30 秒的连接池阻塞。
- 新增 `scripts/check_p7_resilience.ps1`，顺序演练 Python、Redis 和 MySQL
  故障，并在 `finally` 中恢复依赖。
- 故障脚本兼容 Windows PowerShell 5.1：GET 不再错误携带空 JSON body，
  503 响应优先读取 `ErrorDetails.Message`，Redis 认证状态故障断言使用
  `AUTH_STATE_UNAVAILABLE`。

## 2. 自动化门禁

### Java

使用便携 JDK 17 执行：

```text
mvnw.cmd -q clean verify
28 suites
127 tests, 0 failures, 0 errors, 0 skipped
exit code 0
```

测试包含真实 MySQL 8.0 和 Redis 7.4 Testcontainers，覆盖 Flyway、JPA、
Redis、IAM/RBAC、会话与任务、AI 编排、文档索引、畜牧业务边界、审计和
Prometheus 权限。

### Python 与静态门禁

```text
pytest -q
606 passed, 3 skipped

Node syntax: 4 files passed
PowerShell syntax: 6 files passed
git diff --check: passed
```

未声称运行 Ruff；当前环境没有把 Ruff 作为本阶段已执行证据。

## 3. Compose 与故障演练

Compose 重建后，`java-app`、`python-ai`、`mysql`、`redis` 均为
`running / healthy`。

`scripts/check_p7_resilience.ps1` 实际结果：

```text
prometheus: PASS
python-outage: PASS, detectionMs=1878
redis-outage: PASS
mysql-outage: PASS, javaResponseMs=4562, pythonCalled=false
```

演练验证：

- Python 停止时 readiness 503，liveness 仍为 200；恢复后 readiness 200。
- Redis 停止时受保护 API fail-closed 为 503
  `AUTH_STATE_UNAVAILABLE`；恢复后可重新访问。
- MySQL 停止时 Java 业务写入在约 4.6 秒内返回 503
  `DATASTORE_UNAVAILABLE`，对应 request ID 未出现在 Python 日志中，证明
  Java 持久化成功前不会越过边界调用 AI 服务。
- 脚本结束后四个核心服务全部恢复 healthy。

## 4. Prometheus 权限与 AI 指标

真实 HTTP 验收结果：

- 匿名访问 `/actuator/prometheus`：401。
- 普通 `USER`：403。
- `ADMIN`：200。
- 创建会话并完成真实 Java -> Python 聊天调用后，Prometheus 出现
  `livestock_ai_calls_total` 和 `livestock_ai_duration_seconds`。
- 验收 AI 任务状态为 `SUCCEEDED`。

用于 403 验证的临时普通用户在检查结束后已禁用。

## 5. Codex 内置浏览器验收

由于内置浏览器禁止直接访问 loopback/私网代理，本次在用户明确授权后使用
一次性 Cloudflare Quick Tunnel 提供随机 HTTPS 地址。只转发 Java 8080，
没有发布 MySQL、Redis 或 Python 端口。

浏览器实际完成：

- 打开企业工作台登录页。
- 首次登录被 CORS allowlist 以 403 拒绝，证明默认配置 fail-closed。
- 临时将随机 HTTPS origin 加入 Java CORS allowlist 后，使用已有测试
  `ADMIN` 登录成功。
- 页面显示 `Java UP`、`Python AI UP`。
- 浏览既有会话，确认 RAG 引用、工具调用链和安全决策可见。
- 从页面发送“奶牛突然停止采食并精神沉郁”的新消息。
- Java 会话/任务层和 Python Agent 链路完成，页面显示：
  `ANSWERED`、`SUPPORTED`、风险 `LOW`、安全决策 `ALLOWED`，并展示
  `supervisor`、`livestock_rag_search`、`grounded_answer_agent`、
  `verifier_agent`、`safety_agent`、`response_agent`。
- 刷新页面后仍保持 `admin / ADMIN` 登录态，新消息和 AI 回答从持久化会话
  中完整恢复，context version 更新为 2。

Compose 使用 `settings.compose.yaml` 的固定 fake RAG/mock 模型，返回内容是
确定性测试夹具。因此本次浏览器验收证明的是 Java/Python 集成、会话持久化、
引用与工具链展示和安全状态，不把固定回答声明为真实模型质量或真实医学效果。

验收结束后：

- 内置浏览器临时标签页已关闭。
- `codex-browser-cloudflared` 容器已删除，随机公网地址失效。
- Java 已以空 `CORS_ALLOWED_ORIGINS` 重建并恢复 healthy。
- 四个核心服务全部 healthy。
- Compose named volumes 未删除。

## 6. 阶段结论

P7.1 的结构化日志、Prometheus、AI 指标、权限控制、依赖故障恢复、
MySQL 快速失败、自动化门禁和真实浏览器验收均已闭环，可以进入 P7.2：
统一发布门禁、安全扫描以及 stub/real 性能记录。
