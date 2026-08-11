# P2 Java 骨架与最小 Compose 阶段报告

日期：2026-07-30

分支：`codex/java-enterprise-integration`

状态：完成

## 1. 已实现范围

- `java-app/`：Java 17、Spring Boot 3.5.7、Maven Wrapper。
- Spring Web、Validation、Data JPA、Data Redis、Actuator。
- MySQL 8.0、Flyway、Hibernate `ddl-auto=validate`。
- 统一成功/错误响应、request ID 生成与透传、MDC 清理。
- Logstash JSON 结构化日志和 request ID 关联。
- 独立 liveness/readiness health group。
- readiness 覆盖 MySQL、Redis 和受 Bearer token 保护的 Python API。
- `GET /api/v1/system/status` 聚合 MySQL、Redis、Python AI 三项依赖状态。
- Testcontainers MySQL/Redis 基础设施测试。
- Java、Python、MySQL、Redis 四服务 Compose。
- 仅 Java 服务发布到宿主机回环地址。
- MySQL/Redis/AI token 缺失时 Compose fail-closed。
- Java/Python 应用容器使用非 root 用户。
- Compose 使用明确的 fake RAG/mock 模型配置，不声称真实 RAG 可复现。

P3 的 IAM/JWT/RBAC、P4 的会话/消息/任务、P5 的 AI 业务代理与韧性、
P6 的可靠索引任务均未在 P2 提前实现。

## 2. Java 自动化门禁

通过便携 JDK 17 实际执行：

```text
mvnw.cmd -B -ntp clean verify
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Testcontainers 集成测试覆盖：

- 空 MySQL 数据库首次执行 V1 Flyway migration；
- 第二次 `migrate()` 执行 0 条，`validate()` 通过；
- JDBC `SELECT 1`；
- Redis set/get 与健康连接；
- Java 使用 Bearer token 和 request ID 调用 Python stub；
- 三依赖正常时 readiness 200；
- Python 依赖 503 时 Java readiness 503、liveness 仍为 200；
- Python 恢复后 readiness 回到 200。

证据：

- `.tmp_tests/p2_java_verify_post_logging/summary.json`
- `.tmp_tests/p2_java_verify_post_logging/maven_verify.log`

## 3. Compose 自动化门禁

验证结果：

- `docker compose config --quiet` 通过；
- Java、Python 两个应用镜像构建通过；
- MySQL、Redis、Python、Java 全部 `healthy`；
- Java liveness：200 / `UP`；
- Java readiness：200 / `UP`；
- Java 聚合依赖：MySQL、Redis、Python AI 全部 `UP`；
- 仅 `java-app` 存在宿主机端口绑定；
- Python 停止时 liveness 200、readiness 503；
- Python 重启后 readiness 恢复 200；
- Java 应用日志为合法 JSON；
- request ID 已进入结构化日志 MDC 字段。

证据：

- `.tmp_tests/p2_compose_post_logging/summary.json`
- `.tmp_tests/p2_compose_post_logging/compose.log`

## 4. Google Chrome 手工验收

用户在 Google Chrome 中实际访问并提供截图，确认：

- `/actuator/health/liveness` 返回 `{"status":"UP"}`；
- `/actuator/health/readiness` 返回 `{"status":"UP"}`；
- `/api/v1/system/status` 返回 MySQL、Redis、Python AI 全部 `UP`。

验收时 Windows 将 `7998–8097` 注册为 TCP 排除范围，Docker 无法绑定默认
`127.0.0.1:8080`。使用 Compose 已有的 `JAVA_PORT` 覆盖绑定到
`127.0.0.1:80` 完成验收，没有修改系统端口策略，也没有扩大到非回环地址。

## 5. 阶段结论

P2 的代码、自动化测试、Compose 故障恢复和真实浏览器验收全部通过，可以进入 P3。
