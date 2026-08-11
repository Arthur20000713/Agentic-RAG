# Agentic RAG V7 handoff

Last updated: 2026-08-11

## Git 与工作区

- Repository: `C:\Users\DELL\PycharmProjects\PythonProject\Agentic RAG`
- Current branch: `codex/java-enterprise-integration`
- 工作树包含 P0–P7 的大量已修改/未跟踪文件，以及用户/前序工作；没有在本轮 stage、commit 或 push。
- 在确认文件归属前不要批量 `git add .`，不要覆盖或清理无关修改。
- 不要提交 `.env`、secret、`.tmp_tests`、runtime DB、日志、索引、`.venv`、`.deps`、`.idea`。
- 不要删除现有 Docker Compose named volumes。

## 当前完成状态

V7 P0–P7 的本机实现与验收已闭环：

- P7.1 稳定性/可观测性：PASS；
- P7.2 安全/性能/发布门禁：PASS；
- P7.3 架构/API/迁移/运维/演示/双简历证据：PASS（本机工作树）。

最终入口：

- `README.md`
- `docs/V7_ARCHITECTURE_AND_BOUNDARIES.md`
- `docs/API_SPEC.md`
- `docs/V7_MIGRATION_RUNBOOK.md`
- `docs/V7_OPERATIONS_RUNBOOK.md`
- `docs/DEMO_SCRIPT.md`
- `docs/P7_RESUME_EVIDENCE.md`
- `docs/reports/P7_FINAL_DELIVERY_REPORT.md`

## As-built 架构

- Spring Boot 是唯一外部入口：IAM/RBAC、会话、消息、任务、审计、文档和畜牧业务。
- MySQL 是唯一业务事实源；Flyway V1–V7 管理 schema。
- Redis 保存 refresh family/撤销/TTL 和可重建的 opaque AI context。
- FastAPI 负责 RAG、LangGraph Agent、动态问诊、模型、安全、评测与短期 execution record。
- Java 通过 `/internal/v1` + service Bearer 调用 Python；用户 JWT 不进入 Python。
- 只有 Java 发布 `127.0.0.1:8080`。

重要边界：当前 Compose 固定 `RAG_QUERY_MODE=fake`，用于可重复集成/性能回归。Sibling RAG-SERVER 的 MCP stdio 本机路径仍存在，但没有打包进 Docker；不要宣称 Compose 已部署真实 RAG 或 P7 数字是真实模型性能。

## 最新验证证据

- Java clean verify：127 tests，0 failures/errors/skipped；
- Python full pytest：611 passed，3 skipped；
- source secret scan：0 findings；
- final Java/Python images：0 个已有修复版本的 HIGH/CRITICAL；
- Compose build/health/login/port boundary：PASS；
- Python/Redis/MySQL failure drills：PASS；
- business stub 50 VU/5m：15,001 requests，0 errors，p95 27.83 ms；
- AI stub 20 sessions/5m：4,932 requests，0 errors，p95 1.684 s；
- Codex in-app browser：login、UP status、new conversation、Chinese query、citations/tools、reload persistence PASS。

证据报告：`docs/reports/P7_SECURITY_PERFORMANCE_RELEASE_REPORT.md`。

## 当前运行环境

Compose 四个业务容器已运行，Java healthy；浏览器验收的临时 Cloudflare tunnel 已删除，Java `CORS_ALLOWED_ORIGINS` 已恢复为空。named volumes 未删除。

不要在文档或命令输出中打印容器环境里的密码/token。若 Compose 复用旧 MySQL volume，bootstrap 环境变量不会重置已有管理员密码。

## 常用命令

```powershell
# 启动/保留数据停止
docker compose up --build --detach --wait
docker compose down

# Java
.\scripts\check_p2_java.ps1 -OutputDir .tmp_tests\java

# Python
.venv\Scripts\python.exe -m pytest -q

# Compose / resilience / security
.\scripts\check_p2_compose.ps1 -OutputDir .tmp_tests\compose
.\scripts\check_p7_resilience.ps1
.\scripts\check_p7_security.ps1 -OutputDir .tmp_tests\security

# 完整发布；含两个 5 分钟 stub profile
.\scripts\check_release_v7.ps1 -IncludePerformance
```

`-Skip*` 不能替代完整验收。真实 AI benchmark 必须显式 `--profile ai-real --confirm-real-ai` 并记录模型、知识库和规模。

## 后续最优先事项

1. 审查 dirty worktree 的文件归属，把 P0–P7 拆成可审查提交；不要夹带用户无关修改。
2. 在需要时固定 sibling RAG-SERVER 版本并完成 Docker 打包或独立内部服务，关闭 ADR-0003。
3. 在明确真实模型/collection 的环境中重跑 real quality gate 和 ai-real benchmark，再决定是否更新简历数字。
4. 若面向更接近生产的部署，再补备份恢复演练、告警、HA、secret manager 和合规评审；当前项目没有这些能力。

## 安全规则

- Never print or commit API keys, JWT secrets, service tokens, refresh tokens or database passwords.
- Do not expose MySQL, Redis or Python ports to untrusted networks.
- Do not use `docker compose down -v` on the existing project.
- Do not describe fake/stub results as real RAG/model quality.
- Do not claim high availability, bank-grade production, compliance certification or model-provider exactly-once.
