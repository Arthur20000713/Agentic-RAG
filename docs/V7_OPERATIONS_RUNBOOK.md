# V7 本地部署与运维 Runbook

本文面向本机演示、开发验收和故障定位。当前系统不是公网生产、高可用或合规认证环境。

## 1. 首次启动

前置条件：Docker Desktop/Compose。只有执行源码测试和发布门禁时才额外需要 Python 3.12、JDK 17、Node.js 和 `rg`。

```powershell
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

编辑本地 `.env`，替换所有 `change-me`，至少设置独立的 MySQL、Redis、JWT、bootstrap admin 和 Java→Python service token。不要提交 `.env`。同源 Java UI 的 `CORS_ALLOWED_ORIGINS` 保持为空。

```powershell
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose up --build --detach --wait
```

打开 `http://127.0.0.1:8080/`，使用 `.env` 中的 bootstrap admin 登录。bootstrap 只在数据库中不存在该用户时创建账号；复用旧 volume 时，修改 `.env` 不会重置既有密码。

停止服务但保留数据：

```powershell
docker compose down
```

日常操作不要使用 `docker compose down -v`。MySQL、Redis、Python execution、上传文件和 RAG 索引都位于 named volumes。

## 2. 健康与网络边界

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/actuator/health/liveness
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/actuator/health/readiness
docker compose ps
```

- liveness 只反映 Java 进程；依赖停止时应继续为 200。
- readiness 汇总 MySQL、Redis 和 Python AI；任一关键依赖不可用时返回 503。
- `/api/v1/system/status` 需要登录后的 Bearer token。
- 只有 Java 应有宿主机端口；MySQL、Redis、Python 不应发布端口。

自动验收：

```powershell
.\scripts\check_p2_compose.ps1 -OutputDir .tmp_tests\compose-check
```

该脚本会构建、等待健康、登录、验证受保护状态接口和端口暴露。它不会删除 named volumes。

## 3. 日志与 request ID

```powershell
docker compose logs --tail 200 java-app
docker compose logs --tail 200 python-ai
docker compose logs --since 10m java-app python-ai
```

Java 使用结构化 JSON 日志。排障时从响应或 `X-Request-ID` 取得 request ID，再同时检索 Java 日志、审计日志与 Python trace；不要在工单中复制 JWT、refresh token、service token、完整 prompt 或未脱敏问诊内容。

## 4. Prometheus 指标

`/actuator/prometheus` 需要 `AUDIT_READ` 权限。除 JVM/Hikari 指标外，AI 关键指标为：

- `livestock_ai_calls_total{operation,outcome}`；
- `livestock_ai_duration_seconds{operation,outcome}`。

operation 覆盖 chat、chat reconciliation、measurement、document index submit/reconciliation。业务 outcome（例如 LOW_CONFIDENCE、SAFETY_REFUSAL）不是传输失败。

## 5. 常见故障

### Python AI 不可用

现象：readiness 503；Java liveness 200；AI 请求快速失败或进入可对账状态。

```powershell
docker compose logs --tail 200 python-ai
docker compose restart python-ai
```

恢复后等待 Java readiness 200。chat 不做盲目自动重试；响应丢失按 operation ID 查询 Python execution record。

### Redis 不可用

现象：readiness 503；认证相关受保护 API 返回 503 / `AUTH_STATE_UNAVAILABLE`。这是 fail-closed 设计。

```powershell
docker compose restart redis
```

Redis context 是可重建缓存，但 refresh family/撤销状态不可用时不能放行认证。

### MySQL 不可用

现象：readiness 503；业务写入返回 503 / `DATASTORE_UNAVAILABLE`。Java 必须在持久化业务状态失败时停止，不先调用 Python。

```powershell
docker compose restart mysql
```

### 文档索引长期未完成

检查 Java task/document 状态、`operationId`、Python AI 日志和共享 object key。`SUBMIT_UNKNOWN` 表示提交结果不确定，`DocumentIndexReconciler` 会查询 `/internal/v1/ai/operations/{operationId}`；不要手工重复创建具有不同 idempotency key 的同一任务。

完整故障演练：

```powershell
$env:BOOTSTRAP_ADMIN_USERNAME = Read-Host 'Admin username'
$env:BOOTSTRAP_ADMIN_PASSWORD = Read-Host 'Admin password'
.\scripts\check_p7_resilience.ps1
```

脚本会依次停止并恢复 Python、Redis 和 MySQL，最终等待 readiness 重新为 200。

## 6. 数据、备份和升级边界

| Volume | 内容 | 备份要求 |
| --- | --- | --- |
| `mysql-data` | 用户、业务、会话、任务、审计 | 使用 MySQL 一致性备份方案 |
| `redis-data` | refresh family、撤销、opaque context | 可重建 context 不等于认证状态可丢失 |
| `python-ai-data` | 短期 execution record | 用于 response-loss reconciliation |
| `knowledge-uploads` | 上传原文件 | 与 MySQL 文档元数据一致备份 |
| `rag-index-data` | 索引持久化目录 | 当前 fake profile 不代表真实 RAG 备份完成 |

仓库没有生产级自动备份/恢复或灾难恢复演练。升级前必须另行备份并验证恢复。Flyway 只做前向 schema migration，`ddl-auto=validate` 不代替备份。

SQLite→MySQL 业务迁移见 `V7_MIGRATION_RUNBOOK.md`。

## 7. 密钥与配置变更

- MySQL/Redis 密码变更必须同步服务端与 Java 客户端配置，并安排维护窗口。
- `JWT_SECRET` 轮换会使旧 access token 失效；refresh family 的迁移/撤销策略需同时评审。
- `AI_SERVICE_TOKEN` 必须同步 Java 与 Python；变更不一致会使 Python readiness/调用失败。
- bootstrap admin 密码不是持续的账号重置机制。
- 仅为明确前端 origin 设置 CORS；临时 origin 验收结束后恢复为空。
- Compose 的 `AI_CHAT_MAX_CONCURRENT_CALLS` 默认为 20，代码默认仍为 8；调整后必须重跑 AI stub 并观察 409/`AI_BUSY`。

## 8. 发布门禁

```powershell
.\scripts\check_release_v7.ps1 -IncludePerformance
```

完整门禁包含 Java clean verify、Python 全量 pytest、静态检查、Compose、故障演练、安全扫描和两组 5 分钟 stub 性能。`-Skip*` 只用于定位问题，带跳过项的摘要不能替代完整验收。

真实 AI 性能必须单独使用 `benchmark_p7.py --profile ai-real --confirm-real-ai`，并填写模型、知识库及规模；stub 结果不能作为真实模型指标。

手动浏览器验收不在脚本内。发布前还应完成登录、状态、建会话、AI 回答、引用/安全状态和刷新持久化检查。

## 9. 新环境验收说明

当前本机已通过：Docker 镜像重建、四服务健康、只有 Java 发布端口、首次 Flyway 在隔离 MySQL Testcontainer 执行、浏览器登录/问诊/刷新以及服务重启后的数据保持。

本 runbook 不通过删除现有 named volumes 模拟 clean install。真正 clean clone 应使用独立环境/项目名和独立数据资源，完成验收后按组织数据保留策略清理；不得误删现有项目 volume。
