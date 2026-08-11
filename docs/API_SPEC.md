# V7 API 导航与语义

两份 OpenAPI YAML 是字段、状态码和 schema 的权威合同：

- `contracts/business-api-v1.yaml`：浏览器/客户端调用的 Java 公共 API；
- `contracts/ai-service-v1.yaml`：Java 调用 Python 的内部 AI API。

本文只解释边界和跨接口语义，不复制完整 schema。

## 1. Java 公共 API

Base URL：`http://127.0.0.1:8080`。用户 JWT 在 Java 终止，除登录、刷新、静态页面和 health probes 外均需 Bearer access token。

| 领域 | 路径 | 说明 |
| --- | --- | --- |
| 认证 | `POST /api/v1/auth/login` | 创建 access/refresh pair 与 Redis refresh family |
| 认证 | `POST /api/v1/auth/refresh` | 原子消费并轮换 refresh token |
| 认证 | `POST /api/v1/auth/logout` | 撤销当前 token family |
| 用户 | `/api/v1/users...` | 用户列表、详情、创建、状态和角色管理 |
| 会话 | `/api/v1/conversations...` | 会话 CRUD、消息历史与 AI 消息提交 |
| 文档 | `POST /api/v1/documents` | multipart 上传并创建可靠索引任务 |
| 文档 | `GET /api/v1/documents/{documentId}` | 查询文档/索引状态 |
| 体尺 | `POST /api/v1/measurements/analyze` | 使用 Java 授权后的动物快照调用 Python 分析 |
| 任务 | `/api/v1/tasks...` | 按权限查询任务列表/详情 |
| 审计 | `GET /api/v1/audit-logs` | 需要 `AUDIT_READ` |
| 系统 | `GET /api/v1/system/status` | 登录后查看 MySQL、Redis、Python 状态 |
| 健康 | `/actuator/health/liveness`、`/readiness` | 匿名容器 probes |
| 指标 | `GET /actuator/prometheus` | 需要 `AUDIT_READ` |

角色为 `ADMIN`、`VET`、`AUDITOR`、`USER`；细粒度权限包括 `USER_MANAGE`、`AI_CHAT`、`MEASUREMENT_ANALYZE`、会话 own/all read、`DOCUMENT_UPLOAD`、任务 own/manage、`TRACE_READ` 和 `AUDIT_READ`。最终授权以 OpenAPI 的 `x-required-authority`、Spring 方法授权和资源所有权检查为准。

## 2. Java 响应格式

成功：

```json
{
  "requestId": "req_xxx",
  "data": {},
  "timestamp": "2026-08-11T04:49:37Z"
}
```

失败：

```json
{
  "requestId": "req_xxx",
  "error": {
    "code": "ERROR_CODE",
    "message": "safe message"
  },
  "timestamp": "2026-08-11T04:49:37Z"
}
```

客户端可传 `X-Request-ID`；Java 校验后回显并贯穿审计与 Python trace。错误响应不返回堆栈、token 或下游敏感正文。

## 3. 幂等、版本和任务语义

- 产生业务副作用的 AI/上传请求使用 `Idempotency-Key`；相同 key + 相同规范化请求返回既有结果，不同 payload 冲突返回 409。
- 会话消息提交必须携带当前 `contextVersion`。MySQL 是版本权威；版本过期、会话非 ACTIVE 或已有 active operation 返回 409。
- Python 返回 `nextContext` 与下一版本，但只由 Java 在 MySQL 提交成功后更新 Redis opaque context。
- chat、低置信度、追问和 safety refusal 是业务结果，通常返回 HTTP 200；不能把它们当传输失败自动重试。
- 文档索引是异步任务，可经过 `CREATED/RUNNING/SUBMIT_UNKNOWN`，最终到 `SUCCEEDED/FAILED/TIMED_OUT/CANCELLED`。状态只能单调推进。

常见 HTTP 语义：

| 状态 | 含义 |
| ---: | --- |
| 400/422 | 请求格式或业务校验失败 |
| 401 | 未认证、token 无效或 refresh 无效 |
| 403 | 缺权限或资源不属于当前用户 |
| 404 | 资源不存在，或按安全策略不暴露其存在 |
| 409 | 乐观锁、contextVersion、active operation 或幂等冲突 |
| 429 | bulkhead 容量已满，错误码可为 `AI_BUSY` |
| 503 | MySQL、Redis、Python 或认证状态不可用 |
| 504 | 下游 deadline 超时 |

## 4. Python 内部 API

Base URL 仅在 Compose 网络中为 `http://python-ai:8000`。除 health 外使用独立 opaque service Bearer token；Java 不转发用户 JWT。`userId` 只是 Java 已授权后的关联字段，不是 Python 的授权输入。

| 路径 | 说明 |
| --- | --- |
| `POST /internal/v1/ai/chat` | 同步执行 RAG/Agent/问诊/Verifier/Safety |
| `GET /internal/v1/ai/runs/{operationId}` | chat 响应丢失对账 |
| `POST /internal/v1/ai/measurements/analyze` | 体尺 AI 分析 |
| `POST /internal/v1/ai/knowledge/ingestions` | 接受异步文档索引，返回 202 |
| `GET /internal/v1/ai/operations/{operationId}` | 索引 operation 对账 |
| `GET /internal/v1/rag/collections` | 只读 collection discovery |
| `GET /internal/v1/rag/collections/{collection}/documents/{docId}/summary` | collection-scoped 文档摘要 |
| `/internal/v1/health/liveness`、`/readiness` | 匿名容器 probes |

所有业务请求要求 `X-Request-ID`；POST 还要求 `Idempotency-Key`，并与 body 中的 `requestId`/`operationId` 绑定。Python execution record 只用于短期技术对账，不是会话、消息、文档或任务事实。

## 5. RAG 与安全响应约束

- citation 只能来自映射后的检索结果，使用稳定 `sourceUri`；
- 空结果、低置信或检索失败不得编造来源；
- `outcome`、`evidenceStatus`、`riskLevel`、`safety.decision` 和 `toolsUsed` 是可观测业务字段；
- 具体药物剂量、确定性诊断、停药期绕过和无依据引用会进入安全拒答或保守回答；
- Compose 默认 fake RAG 只验证契约和编排，不证明真实知识库质量。

旧 `/api/*` FastAPI 路由保留用于 Python 回归和本机开发，不是 V7 Compose 的客户端入口。
