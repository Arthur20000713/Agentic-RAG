# P5 Java AI 编排验收报告

日期：2026-08-04

分支：`codex/java-enterprise-integration`

## 1. 交付范围

P5 已把同步 AI 主链路收口到 Java 业务层：客户端只访问 Java，Java 在 MySQL 中创建并推进会话、消息和任务，通过带服务令牌的 HTTP 请求调用 Python AI 服务，再把助手消息、任务终态、审计日志和上下文版本原子落库。Python 继续负责 RAG 检索、Agent 编排、问诊流程、模型调用与低置信度/安全决策。

本报告覆盖 Java/Python 编排、幂等恢复、P5.3 静态前端切换和真实 Compose 链路。

## 2. 已验证的可靠性语义

- `Idempotency-Key` 同时作为跨服务 `operationId`，同一请求重放不会重复生成助手消息或审计事件。
- Python 返回格式异常的 HTTP 200 时，Java 将提交视为未知并通过 GET 对账，不盲目重试 POST。
- Java 在崩溃后可从持久化任务重建原请求，并在 Python 尚未领取操作时重新派发。
- Java 与 Python 共享 90 秒恢复租约；Python 可原子接管过期 `RUNNING` 执行记录一次。
- `AI_CHAT_ENABLED=false` 在事务 A 前拒绝请求，不遗留孤立任务或会话占用。
- Redis opaque context 使用版本 CAS，延迟的旧版本写入不会覆盖新版本；MySQL `context_version` 始终是权威值。
- Python 503 的首答与重放保持一致的 `retryable=true` 语义。
- 端到端等待上限为 60 秒，终态并发重放不会错误返回 409。

## 3. 自动化验收

| 验收门 | 结果 |
| --- | --- |
| P4 会话/任务集成测试 | 12/12 通过 |
| P5 AI 编排集成测试 | 7/7 通过 |
| Java `clean verify` | 109 tests，0 failures/errors/skips |
| Python execution/internal API | 44 passed |
| Business OpenAPI | P5，16 paths，无缺失 schema 引用 |
| AI OpenAPI | 9 paths，无缺失 schema 引用 |
| `git diff --check` | 通过 |
| Java 可执行 JAR | 构建成功 |

## 4. 真实 Compose E2E

在 MySQL、Redis、Python AI、Java 四服务健康的 Compose 环境中，已通过真实 HTTP 完成：管理员登录、创建业务用户、用户登录、两轮会话、低置信度回答、安全拒答、系统依赖状态和审计查询。

结果：

- 四个 AI 任务均为 `SUCCEEDED`，进度为 100；
- 每个 operation 恰好生成一条助手消息和一条 `AI_QUERY_COMPLETED` 审计；
- 两轮主会话 MySQL `context_version=2` 且 `active_operation_id=NULL`；
- Redis opaque context 为 `contextVersion=2`，与 MySQL 权威版本一致；
- Java 是唯一对外端口，Python 未发布宿主机端口。

## 5. P5.3 前端切换

静态 SPA 已迁到 `java-app/src/main/resources/static/`，Spring Security 只匿名放行入口和静态资源，业务 API 继续要求 JWT。前端令牌仅写入 `sessionStorage`，支持登录、刷新、退出、会话列表、新建、重命名、删除、任务轮询和两轮消息历史。消息提交使用 MySQL 权威 `contextVersion` 和每次唯一的 `Idempotency-Key`，不再请求 Python `/api`。

页面展示助手的 outcome、risk、evidence status、sources、tools used、follow-up 和 safety decision。Java 静态契约测试会拒绝旧 `/api/chat`、`X-Client-ID` 等 Python 前端调用方式。

## 6. 浏览器验收

Java readiness 通过宿主机和临时只读端口转发均返回 `{"status":"UP"}`。Codex 内置浏览器不能直接访问回环或私网字面地址，因此使用同一临时转发的 Windows 主机名打开页面；未改变应用代码、Compose 网络或数据卷。

浏览器实际完成并可见确认：

- 打开 Java origin 登录页，架构说明和登录表单正常显示；
- 使用新建的普通用户登录，工作台显示 `Java UP`、`Python AI UP`；
- 打开已有真实引用会话，显示 `SUPPORTED`、2 个来源、7 个工具和 `ALLOWED` 安全决策；
- 点击“高温饲喂”示例并发送第二轮消息；
- 页面出现第二组用户/助手消息，`contextVersion` 从 1 推进到 2，会话列表时间同步更新。

部署级 HTTP E2E 同时验证了新用户创建与登录、系统依赖、建会话、消息提交、任务 `SUCCEEDED`、助手 `ANSWERED`、MySQL 两条消息和 context version 推进。

## 7. 阶段结论

P5 验收通过。客户端入口、身份、会话、任务、审计和静态托管均归 Java；RAG、Agent、模型、安全和评测能力继续归 Python，形成可用于双版本简历的完整企业 AI 集成闭环。
