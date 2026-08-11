# P4 会话、任务与停机迁移验收报告

日期：2026-07-30

分支：`codex/java-enterprise-integration`

## 1. 结论

P4 已形成可验证的 Java 业务闭环：

- Spring Boot 管理会话、用户消息和 `AI_QUERY` 任务；
- MySQL 是业务状态与 `context_version` 的唯一权威；
- 首次提交返回 `202 + Location`，同载荷幂等重放返回
  `200 + Idempotent-Replayed: true`；
- 会话占用、用户消息、任务和成功审计在事务 A 中原子提交；
- 跨用户资源访问按权限语义稳定返回 403 或防枚举 404；
- 历史 SQLite 数据具备停机迁移、校验、对账和回滚保护；
- Compose 中 MySQL、Redis、Python AI、Java 四个服务均为 healthy。

P4 不调用 Python 执行业务问答，也不完成事务 B。Java HTTP 调用
Python、Redis opaque AI context、助手消息落库、任务终态和
`context_version + 1` 属于 P5。

## 2. 主要实现

### 2.1 会话与消息

- 创建、分页列表、详情、稳定排序的最近消息；
- 重命名、归档/恢复、带版本的软删除；
- `@Positive` 路径 ID、DTO 校验和统一 400；
- 普通用户只能访问本人会话，管理型读取权限与所有权判断分离；
- bounded history 防止 Java 向后续 Python 服务传递无界上下文。

### 2.2 任务与幂等

- `biz_task` 保存所有者、会话、任务类型、operation ID、请求哈希和状态；
- `(owner_id, operation_id)` 是业务幂等唯一键；
- 请求哈希覆盖会话 ID、任务类型、上下文版本和内容；
- 同键同载荷只产生一个任务和一条用户消息；
- 同键异载荷稳定返回 `409 IDEMPOTENCY_KEY_REUSED`；
- 同一用户的并发提交通过用户行锁串行化，避免跨会话幂等竞态；
- `X-Request-ID` 仅作为关联元数据，V5 移除其全局唯一约束并保留普通索引。

### 2.3 事务与审计

事务 A 同时写入：

1. 会话 active operation 与 `last_message_at`；
2. `AI_QUERY` CREATED 任务；
3. USER 消息；
4. `AI_QUERY_SUBMITTED` 审计。

审计写入失败会使上述业务写入一起回滚。幂等异载荷冲突的失败审计在外层
事务回滚后通过新事务写入，避免审计外键和用户行锁自死锁，并保留
client IP、User-Agent、请求 ID 以及幂等键摘要，不保存原始幂等键或正文。

### 2.4 数据库迁移

- V3：`conversation`、`conversation_message`、`biz_task`；
- V4：legacy import run、owner map 和 ID map；
- V5：移除 `(request_id, role)` 全局唯一索引，新增
  `idx_conversation_message_request_id` 普通索引。

Flyway 已在全新 Testcontainers MySQL 上按 V1–V5 应用，并在现有 Compose
named volume 上向前升级到版本 5。没有删除或重建 named volume。

## 3. SQLite 停机迁移

迁移工具：`scripts/migrate_p4_sqlite_to_mysql.py`

安全约束：

- apply 必须读取独立备份，禁止直接读取 live 写库；
- 校验 expected SHA256、SQLite integrity/schema/FK 和 WAL 静止状态；
- MySQL `GET_LOCK`、单事务、UTC、ledger/map 和失败回滚；
- legacy owner 映射为禁用 shadow user；
- 空答案或错误 response 拒绝迁移；
- 对话、消息、任务、映射、外键、时间和抽样哈希对账；
- AI_QUERY task map 从持久化映射表全量反查；
- 历史 `request_hash` 与 Java `IdempotencyHasher` 字节协议一致。
- 隔离 MySQL 集成测试执行真实 apply，并覆盖持久化 map 篡改后的全事务回滚。

真实 `data/app.db` dry-run：

| 项目 | 数量 |
|---|---:|
| conversations | 28 |
| messages | 98 |
| historical AI_QUERY tasks | 49 |
| shadow users | 2 |
| ID maps | 175 |

源文件 SHA256：

`9F1FC4CEED472FF818ACCCE37492B15E61385CA0D0C9627DBCA18BC92F056640`

dry-run 无 warning，源 SQLite 的哈希和修改时间未变化。P4 没有执行真实
MySQL 导入。

## 4. 验证证据

### 4.1 自动化测试

- Java `clean verify`：18 个测试类，78 tests，0 failure，0 error，
  0 skipped，测试后成功生成 Spring Boot JAR；
- `P4ConversationTaskIntegrationTest`：12 tests 全通过；
- SQLite/真实隔离 MySQL 迁移：16 tests 全通过；
- `InfrastructureIntegrationTest`：6 tests 全通过，包含带既有消息的
  V4→V5 单步升级；
- OpenAPI 3.1：16 paths、150 个本地 `$ref` 全部解析；
- P4 九个受保护 operation 的 503 合同覆盖：9/9；
- Redocly minimal lint：结构与语义通过。跳过的
  `operation-summary` 是 P3 既有风格规则，不影响合同结构。

### 4.2 真实 HTTP 主链路

已验证：

- readiness 与 system status 返回 200；
- 管理员创建用户、用户登录、创建会话；
- 首次消息提交 202；
- 同载荷重放 200，响应头为 `Idempotent-Replayed: true`；
- 异载荷重用返回 409 `IDEMPOTENCY_KEY_REUSED`；
- 跨所有者资源返回 404，缺少整类权限返回 403；
- 同一 operation 只有一个 task 和一条 USER message；
- 审计中未发现正文、secret 或原始幂等键。

### 4.3 依赖故障演练

MySQL 停机：

- 受保护接口：503 `DATASTORE_UNAVAILABLE`；
- 登录：503 `DATASTORE_UNAVAILABLE`；
- liveness：200 `UP`；
- readiness：503 `DOWN`；
- MySQL 恢复后服务恢复 healthy。

Redis 停机：

- 登录、刷新、登出、受保护接口：
  503 `AUTH_STATE_UNAVAILABLE`；
- liveness：200 `UP`；
- readiness：503 `DOWN`；
- Redis 恢复后登录成功。

### 4.4 浏览器验收

用户提供的真实 Google Chrome 截图确认：

- `http://127.0.0.1/actuator/health/readiness` 显示
  `{"status":"UP"}`；
- `http://127.0.0.1/api/v1/system/status` 显示 MySQL、Redis 和
  Python AI 均为 `UP`。

Codex 本轮也实际创建了内置浏览器和 Chrome 受控标签，并分别导航
`127.0.0.1` 与 `localhost`；浏览器自动化控制层统一返回
`ERR_BLOCKED_BY_CLIENT`。Chrome 扩展通信和标签创建正常，因此这是控制层
对回环地址的限制，不是服务不可达。最终服务状态另由真实 HTTP、容器
healthcheck、MySQL Flyway 版本和用户 Chrome 页面四类证据交叉确认。

## 5. 审查问题与关闭情况

第一轮审查发现并关闭：

1. `request_id` 全局唯一误用：V5 改为普通索引，并增加跨会话复用回归；
2. P4 OpenAPI 缺 503：九个受保护 operation 全部补齐；
3. 路径 ID 合同与实现漂移：会话与任务详情 ID 增加 `@Positive`；
4. 幂等冲突审计缺请求来源：回滚后审计保留 IP 和 User-Agent；
5. 迁移 task hash 与 Java 算法不一致：改为相同字节协议并增加固定向量；
6. task map 只做内存抽样：改为持久化表全量反向对账。
7. 非唯一 request ID 仍有单结果仓储方法：删除未使用的错误契约；
8. V5 只测空库最终态：增加独立 MySQL 的 V4 存量数据升级测试；
9. 迁移对账缺真实 MySQL 路径：增加成功 apply、map 篡改和完整回滚测试。

经过三轮审查，最终未保留 P0、P1 或 P2 问题。

## 6. P5 入口

P5 从当前事务 A 之后继续：

1. Java 构造有限历史、opaque context 和 operation ID；
2. Java 通过内部 HTTP 合同调用 Python chat/measurement；
3. 增加 timeout、错误映射、circuit breaker 和 bulkhead，chat POST 默认不重试；
4. 成功时执行事务 B：助手消息、任务终态、审计和
   `context_version + 1`；
5. Redis 保存 opaque AI context cache，MySQL 版本仍是唯一权威；
6. 前端切换到 Java API；
7. 完成登录到真实引用、低置信度、高风险和 Python 超时的 Compose E2E。
