# P6 文档索引与可靠任务验收报告

日期：2026-08-04

分支：`codex/java-enterprise-integration`

## 1. 交付范围

P6 增加由 Java 业务层统一接入的文档上传和可靠 `DOCUMENT_INDEX` 异步任务。Java 负责 JWT/RBAC、文件校验、共享卷交付、MySQL 文档与任务事实、状态对账和审计；Python 负责 object key 二次校验、短期执行记录、租约 worker 和 RAG-SERVER ingestion 调用。Java 与 Python 不共享业务数据库。

## 2. 数据与接口边界

- `POST /api/v1/documents` 接收 PDF 或 UTF-8 文本，要求 `Idempotency-Key`，返回文档和任务。
- `GET /api/v1/documents/{documentId}` 按资源所有权返回文档索引状态；任务继续由 `/api/v1/tasks/{id}` 查询。
- Java 只向 Python 发送相对 object key、size 和 SHA-256，不传宿主机绝对路径。
- Python 内部接口使用 `POST /internal/v1/ai/knowledge/ingestions` 和 `GET /internal/v1/ai/operations/{operationId}`；终态结果返回 `ragDocumentId`、collection、indexed/skipped、chunkCount 和 executionMode。

## 3. 可靠性与安全语义

- Java 将文件写入临时文件，流式计算 SHA-256，验证扩展名、MIME、大小、PDF magic 或 UTF-8 后原子移动到共享卷。
- `(owner_id, client_idempotency_key)`、operation ID、object key 和 task 均有唯一约束；相同 key/相同内容重放既有结果，不同内容返回 409。
- Python 在返回 202 前持久化完整 canonical payload；`ACCEPTED → RUNNING → SUCCEEDED/FAILED/TIMED_OUT/CANCELLED` 终态单调推进。
- worker 原子领取 operation，以 lease token 和 heartbeat 续租；过期 worker 的终态写入会被 fencing 条件拒绝。
- Java 持久化扫描 `CREATED/RUNNING/SUBMIT_UNKNOWN`；POST 响应丢失时先 GET 对账，不存在 operation 时才以同 operation ID 安全重提。
- Python 对 object key 再做固定根目录、symlink、普通文件、扩展/MIME、size、hash、PDF magic/UTF-8 校验。
- `force=false` 固化在 v1，避免绕过内容幂等。

## 4. Compose 边界

`knowledge-uploads` 由 Java 读写、Python 只读；`python-ai-data` 保存 Python execution store；`rag-index-data` 为 RAG 索引预留。初始化容器统一目录权限，Java/Python 镜像使用数值 UID/GID 10001。默认 Compose 仍为 `RAG_QUERY_MODE=fake`：可验证共享卷、校验、任务恢复和跨服务合同，但不能把 FAKE 成功描述为真实向量索引。真实 RAG 仍需固定并容器化 RAG-SERVER 制品后单独验收。

## 5. 验收证据

- 浏览器真实登录、文件选择、上传和轮询通过。文档 `doc_2c06f8b9-b7bd-40dd-8bb4-e1ba09e4806c`、任务 `13` 最终显示“FAKE 模式交付校验通过（VALIDATED）”；刷新页面后 VET 登录态仍有效。
- Node 静态语法、Java 静态前端契约、两份 OpenAPI YAML 和本地 `$ref` 完整性均纳入阶段门禁。
- Python 覆盖 payload 重启恢复、终态 POST replay、文件校验失败、过期 lease/fencing、missing object 和 symlink 拒绝。
- Java 覆盖共享卷校验、同 key replay/冲突、响应丢失对账、唯一业务终态、文档所有权和完成审计。

最终全量测试数字以本分支 P6 总体验收记录为准。

## 6. 阶段结论

P6 文档索引业务闭环和可靠任务语义已形成：Java 是文档与任务事实源，Python 是可对账的执行方，共享文件只通过 object key 交付。默认 Compose 的可靠性验收为 FAKE ingestion；在真实 RAG-SERVER 固定制品、索引卷映射和真实检索回查完成前，不宣称真实知识库入库已经通过。
