# V7 双岗位演示脚本

目标时长 10–15 分钟。公共主线先证明“Java 业务入口调用 Python AI 能力”，再根据岗位选择 AI 或 Java 深挖。默认 Compose 使用 deterministic fake RAG，演示的是契约、编排和工程闭环，不是实际模型效果。

## 0. 演示前准备

```powershell
docker compose up --build --detach --wait
.\scripts\check_p2_compose.ps1 -OutputDir .tmp_tests\demo-compose
```

打开 `http://127.0.0.1:8080/`。准备 `.env` 中的 bootstrap admin 凭据；不要在录屏、终端或投屏中展示 `.env`、JWT 或 service token。

确认：

- 页面可打开；
- Java、Python AI 均显示 UP；
- `docker compose ps` 中只有 Java 发布宿主机端口。

## 1. 公共主线：企业 AI 闭环

### 1.1 登录与边界

使用管理员账号登录。

预期：进入会话工作台，刷新后仍保持登录；浏览器只访问 Java 8080。

讲解：用户 JWT 在 Spring Security 终止，Python 只接受 Java 的内部 service token；Redis refresh family 不保存原始 refresh token。

### 1.2 新建会话并发送中文问诊

点击“新建对话”，输入：

```text
一头奶牛突然停止采食并精神沉郁，应该先检查哪些指标？
```

预期：

- 新会话出现在侧栏；
- 回答展示 outcome、risk、evidence 和 safety decision；
- fake profile 当前可展示 `ANSWERED / LOW / SUPPORTED / ALLOWED`；
- 展示引用来源和工具链；
- 运行详情可看到 request ID、conversation 和 context version。

讲解：Java 先在 MySQL 建立任务/operation，再通过 `/internal/v1/ai/chat` 调用 Python；Python 返回 Agent 结果，Java 原子写入助手消息、任务终态、审计和新 context version。

### 1.3 刷新持久化

刷新页面。

预期：登录态、会话、用户/助手消息和 context version 保持。

讲解：会话与消息的事实源是 MySQL；Redis 只缓存可重建的 opaque AI context，Python 不持有耐久业务会话。

## 2. AI 应用岗深挖

### 2.1 Agent 与证据链

在回答卡片中展示：

- `supervisor`；
- `livestock_rag_search`；
- `grounded_answer_agent`；
- `verifier_agent`；
- `safety_agent`；
- `response_agent`。

讲解：这是 LangGraph 条件图的当前一次实际路径，不代表所有问题都走固定直线。动态问诊使用 case understanding、information gaps、query builder 和 evidence gate，不再依赖固定槽位清单。

### 2.2 低置信度与安全边界

默认 fake Compose 不按输入动态切换所有异常 fixture，因此不要现场把任意问题硬说成低置信度或安全拒答。使用可重复的自动化证据：

```powershell
.\scripts\check_p2_java.ps1 -OutputDir .tmp_tests\demo-java
.venv\Scripts\python.exe -m pytest `
  tests\e2e\test_disease_consultation_flow.py `
  tests\integration\test_eval_runner.py -q
```

展示测试和源码：

- `P5AiChatOrchestrationIntegrationTest` 验证 LOW_CONFIDENCE 空引用与 SAFETY_REFUSAL；
- `grounded_answer_agent.py`、`verifier_agent.py` 验证引用约束；
- `safety_agent.py` 与 final guard 限制具体剂量和确定性诊断；
- `backend/app/evaluation/` 和 `scripts/run_eval.py` 展示 fake/real/Agent/安全分层评测。

边界话术：机制与回归已验证；当前 Compose 不是真实 RAG，当前 real quality gate 未在 P7 重跑，不能宣称真实问答准确率或真实模型性能。

### 2.3 真实 RAG 的可选历史路径

若现场环境明确配置 sibling `RAG-SERVER`，可单独运行：

```powershell
$env:RAG_SERVER_PATH = 'C:\path\to\RAG-SERVER'
.venv\Scripts\python.exe -m pytest -m rag_server
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real-demo
```

只有本次输出不是 skipped 且记录 collection/模型时，才能将其作为当前真实 RAG 证据。不要把 RAG-SERVER 的 embedding、BM25 或 rerank 描述为本仓库自研实现。

## 3. Java / 银行 / 央企研发岗深挖

### 3.1 IAM、权限和审计

展示 `contracts/business-api-v1.yaml` 与以下实现：

- `SecurityConfig`、`JwtService`、`RedisRefreshTokenFamilyStore`；
- `OwnershipGuard` 与用户/会话/任务 controller；
- `AuditService`、`AuditSanitizer`。

讲解：角色与权限分离；用户只能访问自己的业务资源；refresh rotation/replay revoke 依赖 Redis 并 fail-closed；关键业务状态和审计在同一 MySQL 事务提交。

### 3.2 幂等、乐观锁和服务拆分

展示：

- `Idempotency-Key` 与 `contextVersion` contract；
- MySQL `biz_task` operation 唯一约束；
- `MessageSubmissionService`、`AiQueryTransactionService`、`TaskStateMachine`；
- Python execution record 的 operation 查询。

讲解：幂等事实由 MySQL 唯一约束和 Python execution store 共同保证，不宣称“Redis 幂等”。系统保证同一 operation 只接受一个业务结果，不承诺模型计费 exactly-once。

### 3.3 故障演练

```powershell
$env:BOOTSTRAP_ADMIN_USERNAME = Read-Host 'Admin username'
$env:BOOTSTRAP_ADMIN_PASSWORD = Read-Host 'Admin password'
.\scripts\check_p7_resilience.ps1
```

预期证据：

- Python 停止：Java readiness 503、liveness 200，恢复后重新健康；
- Redis 停止：受保护接口 503 / `AUTH_STATE_UNAVAILABLE`；
- MySQL 停止：业务写入 503 / `DATASTORE_UNAVAILABLE`，并验证 `pythonCalled=false`。

讲解：chat 明确使用 timeout/circuit breaker/bulkhead；各 client 有独立 timeout/error mapping，但项目没有宣称全部 AI 调用自动重试或全部使用同一组 Resilience4j 策略。

### 3.4 数据与可靠任务

展示 Flyway V1–V7、`DocumentIndexReconciler`、两个 SQLite→MySQL migration script 和 `V7_MIGRATION_RUNBOOK.md`。

讲解：一次停机迁移而非双写；文档上传使用共享 object key，任务可进入 `SUBMIT_UNKNOWN` 后对账；迁移算法和隔离 MySQL 测试已通过，但没有宣称完成真实生产数据迁移或真实向量入库。

## 4. 性能和安全报告

打开 `docs/reports/P7_SECURITY_PERFORMANCE_RELEASE_REPORT.md`：

- 业务 stub：50 VU，5 分钟，0 错误，p95 27.83 ms；
- AI stub：20 独立会话，5 分钟，0 错误，p95 1.684 s；
- 源码 0 findings；最终镜像 0 个已有修复版本的 HIGH/CRITICAL；
- Java 127 tests；Python 611 passed、3 skipped。

必须同时说明测试环境为 Windows 本机 deterministic fake RAG；不是公网生产 SLA、真实模型性能或绝对“零漏洞”。

## 5. 推荐收尾话术

AI 岗：

> 我没有在应用层重写底层检索，而是把 RAG、动态问诊、Verifier/Safety 和分层评测封装成可测试的 Python AI 服务，再通过版本化契约接入 Java 业务入口。

Java/银行央企岗：

> 这个项目的重点不是给 Python 套一层壳，而是明确业务事实源和服务边界，用 JWT/RBAC、MySQL/Redis、任务状态机、审计、幂等、故障演练和 Compose 把 AI 能力纳入可治理的业务流程。

共同边界：

> 当前是本机可复现的企业 AI 集成系统，不是高可用微服务集群，也没有宣称银行级合规或公网生产上线。
