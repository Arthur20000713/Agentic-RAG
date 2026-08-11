# P3 IAM、RBAC 与资源所有权阶段报告

日期：2026-07-30

分支：`codex/java-enterprise-integration`

状态：功能、自动化和 Compose 验收完成；浏览器自动控制受客户端 loopback 策略限制

## 1. 已实现范围

- Flyway V2：用户、角色、权限、用户角色和 append-only 审计表。
- 预置 `ADMIN`、`VET`、`AUDITOR`、`USER` 角色和规格中的 10 个权限。
- 管理员创建用户、分页查询、状态变更和角色变更。
- BCrypt cost 12 密码散列；登录失败统一响应，避免用户枚举。
- HS256 短期 access JWT，固定校验 issuer、audience、type、时间、签名。
- JWT 包含 `sub`、`jti`、`sid`、`security_version` 和 authorities。
- 256-bit opaque refresh token，Redis 仅保存 SHA-256 摘要。
- Lua 原子 refresh 轮换、used tombstone、并发单次成功和 replay family revoke。
- logout 仅以当前 Bearer access token 的 `sid` 撤销当前 family，不接收冗余
  refresh token，避免跨 family 撤销。
- 每个受保护请求同时校验 Redis family、数据库用户状态和 security version。
- 用户禁用或角色变更后，旧 access token 立即失效。
- 方法级 RBAC、统一 401/403/503 JSON、request ID 透传。
- Redis 认证状态故障统一 fail-closed 为
  `503 AUTH_STATE_UNAVAILABLE`。
- CORS allowlist、stateless Security、禁用 Basic/form login 和默认生成用户。
- 空库、显式启用时创建一次 bootstrap ADMIN；代码和 migration 中无固定凭据。
- 用户创建/状态/角色变更与成功审计使用同一数据库事务。
- 登录、刷新、登出、401/403 和用户变更审计。
- 审计写入前及 API 返回前双层脱敏，覆盖密码、JWT、Bearer/Basic、
  refresh token、service token、API key、prompt/content 和可控字符串字段。
- 审计查询要求 `AUDIT_READ`，支持 request ID 和分页。
- 通用 `OwnershipGuard` 所有权策略合同。
- OpenAPI 3.1 业务接口合同：`contracts/business-api-v1.yaml`。

## 2. Java 自动化门禁

使用便携 JDK 17 串行执行完整构建，避免多个审查代理共享 `target/` 产生竞态：

```text
mvnw.cmd -B -ntp clean verify
Tests run: 54, Failures: 0, Errors: 0, Skipped: 0
15 test classes
BUILD SUCCESS lifecycle completed
```

最终产物：

```text
java-app/target/livestock-business-service-0.1.0-SNAPSHOT.jar
```

自动化覆盖：

- 未认证 401、无权限 403、本人可见和跨用户拒绝；
- 401/403 审计的 actor、result、request ID、method 和 path；
- 最后一个有效 ADMIN 禁用/移除角色保护；
- 大小写重复 username、stale version 和 CORS allowlist；
- JWT 篡改、过期、错误 issuer/audience 和 security version；
- refresh 摘要、TTL、原子轮换、并发和 replay family revoke；
- logout 只撤销当前 family，另一独立登录 family 保持有效；
- Redis 暂停时 login、refresh、protected GET、logout 均统一 503；
- Redis 故障时 liveness 200、readiness 503，恢复后可重新登录；
- 用户创建审计写入失败时业务 insert 同事务回滚；
- 审计所有可控字段、嵌套详情和历史脏数据的双层脱敏；
- Flyway V1/V2 在真实 MySQL Testcontainer 迁移和 Hibernate validate；
- 所有权策略的 owner、跨 owner 和 elevated authority 合同。

## 3. Compose 与真实 HTTP 验收

最终四服务状态：

- `java-app`：healthy；
- `mysql`：healthy；
- `redis`：healthy；
- `python-ai`：healthy。

真实网络 API 验收通过：

- liveness 200 / `UP`；
- readiness 200 / `UP`；
- 匿名访问用户列表 401；
- bootstrap ADMIN 登录；
- ADMIN 创建普通用户；
- 普通用户读取本人成功、用户列表返回 403；
- refresh 正常轮换，旧 token replay 后 successor 和 family access 均失效；
- 无请求体 logout 撤销当前 family，refresh 随即失效；
- ADMIN 按 request ID 查询审计，且响应不包含凭据；
- system status 显示 MySQL、Redis、Python AI 全部 `UP`；
- Redis key 使用 refresh 摘要，不出现原始 token，PTTL 为正且不超过 7 天。

Compose 真实 Redis 故障演练：

- 停止 Redis 后，login、refresh、protected GET、logout 均返回
  `503 AUTH_STATE_UNAVAILABLE`；
- liveness 保持 200 / `UP`；
- readiness 返回 503 / `DOWN`；
- Redis 重启后恢复登录，四服务重新 healthy。

P2 已初始化的 MySQL named volume 保留了原测试数据库用户密码。仅
`docker compose --force-recreate` 不会修改持久卷内的 MySQL 用户凭据。本次没有删除
数据卷，而是复用原 P2 测试凭据完成无损迁移。生产环境变更数据库凭据时必须执行显式
凭据迁移，不能只替换 Compose 环境变量。

Windows 将 `7998–8097` 注册为 TCP 排除范围，因此验收继续使用 Compose 已有的
`JAVA_PORT=80` 覆盖；默认配置仍为 8080，且只有 Java 发布到
`127.0.0.1`。

## 4. 浏览器验收说明

用户先前提供的 Google Chrome 截图已证明 P2 的 readiness 和 system status 页面正常。

P3 最终验收时，Codex 内置浏览器和 Google Chrome 扩展均已被实际打开并尝试访问：

- `http://127.0.0.1/actuator/health/liveness`
- `http://localhost/actuator/health/liveness`

两种浏览器自动控制均在导航层返回 `ERR_BLOCKED_BY_CLIENT`，即客户端禁止自动化访问
loopback。Docker 内网 IP 在 Windows 主机上也不可路由。本报告不把该限制虚报为页面
可见验收通过，也没有通过扩大 Java 监听范围或外网隧道绕过安全限制。

同一 loopback 地址已通过真实 HTTP 客户端完整验证 liveness、readiness、401/403、
登录、refresh、logout、审计和故障恢复。若需要补充 P3 页面截图，可在 Chrome 中手工
打开 `/api/v1/users`，预期显示统一的
`401 AUTHENTICATION_REQUIRED` JSON。

## 5. 递延范围

P3 已完成所有权策略合同和用户资源的真实 IDOR 测试。会话、任务、文档和动物的真实
表与 HTTP 端点在本阶段尚不存在，因此不能声称这些资源的 IDOR 已闭环：

- 会话、消息和同步任务的真实所有权验收在 P4 完成；
- 文档、农场、动物和体尺资源的真实所有权验收在 P6 完成。

## 6. 阶段结论

P3 的 IAM、JWT、refresh family、RBAC、用户所有权、审计、Redis 故障策略和 Compose
闭环已经完成，可以进入 P4。浏览器自动控制的 loopback 限制作为工具环境约束保留，
不掩盖、不绕过。
