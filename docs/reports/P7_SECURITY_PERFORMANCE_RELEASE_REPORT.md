# P7.2 安全、性能与发布门禁报告

## 1. 结论

P7.2 最终状态：**PASS**。

本阶段完成了源码 secret 扫描、Java/Python 镜像漏洞门禁、两组 5 分钟 stub 性能基准、Compose 部署验收、依赖故障演练、完整自动化测试和 Codex 内置浏览器手动验收。所有发布阻断项均已通过。

真实 RAG/模型性能不属于本次 stub 发布结论。只有在显式记录模型、知识库、规模和运行证据后，才允许生成或引用真实 AI 性能数字。

## 2. 安全门禁

入口：

```powershell
.\scripts\check_p7_security.ps1
```

门禁策略：

- 源码扫描覆盖 Git 已跟踪文件和未忽略的新文件；
- 发现项仅输出路径、行号和规则名，不写入候选 secret 原文；
- 镜像扫描优先使用 Docker Scout，未登录时自动回退 Trivy 0.66；
- 阻断存在修复版本的 `HIGH` 或 `CRITICAL` 漏洞；
- 扫描器无法生成有效报告时失败，只有显式 `-SkipImageScan` 才能跳过镜像扫描。

漏洞收敛过程：

| 阶段 | Java 可修复 HIGH/CRITICAL | 处理 |
| --- | ---: | --- |
| 初始镜像 | 25 | 建立 Trivy 基线并定位依赖来源 |
| 第一轮升级 | 20 | 升级 Spring Boot 及基础依赖 |
| 最终镜像 | 0 | 使用受控 BOM/覆盖版本消除剩余可修复项 |

最终 Java 依赖基线包括 Spring Boot 3.5.14、Jackson BOM 2.21.4、Micrometer 1.15.12、Netty 4.1.136.Final、Spring Data BOM 2025.0.12、Spring Framework 6.2.19 和 Tomcat 10.1.55。

最终扫描结果：

| 目标 | 扫描器 | 结果 | Findings |
| --- | --- | --- | ---: |
| 源码 secrets | 脱敏扫描器 | PASS | 0 |
| Java 镜像 | Trivy | PASS | 0 个可修复 HIGH/CRITICAL |
| Python 镜像 | Trivy | PASS | 0 个可修复 HIGH/CRITICAL |

证据：`.tmp_tests/p7-security-final/security-summary.json`。

## 3. 性能基准

测试环境：Windows 11、Intel64 Family 6 Model 141、16 logical CPUs、Python 3.12.7。两组均针对 `http://127.0.0.1:8080`，使用 `RAG_QUERY_MODE=fake` 和 deterministic fake RAG；这些数字不得描述为真实模型性能。

### 3.1 Java 业务读取路径

| 指标 | 结果 |
| --- | ---: |
| 并发 | 50 VU |
| 持续时间 | 300 秒 |
| 请求数 | 15,001 |
| 错误数 / 错误率 | 0 / 0% |
| 吞吐 | 50.00 RPS |
| p50 | 9.53 ms |
| p95 | 27.83 ms |
| p99 | 48.37 ms |

门槛为 p95 不超过 300 ms、错误率不超过 1%，结果 `PASS`。证据：`.tmp_tests/p7-benchmark/business-stub-50vu-5m.json`。

### 3.2 Java → Python AI stub 路径

| 指标 | 结果 |
| --- | ---: |
| 并发 | 20 个独立会话 |
| 持续时间 | 300 秒 |
| 请求数 | 4,932 |
| 错误数 / 错误率 | 0 / 0% |
| 吞吐 | 16.38 RPS |
| p50 | 677.86 ms |
| p95 | 1,684.19 ms |
| p99 | 1,943.06 ms |

门槛为 p95 不超过 5 秒、错误率不超过 1%，结果 `PASS`。证据：`.tmp_tests/p7-benchmark/ai-stub-20vu-5m-final.json`。

早期基线在 bulkhead 默认并发 8 时以 20 并发压测，产生 3,588 个 `AI_BUSY`/HTTP 409。这证明门禁命中了明确的容量边界，而非 `contextVersion` 缺陷。Compose profile 将 `AI_CHAT_MAX_CONCURRENT_CALLS` 调整为 20 后，30 秒回归 600 请求无错误，最终 5 分钟基准同样 0 错误；应用代码默认值仍保持 8。

### 3.3 真实 AI 证据约束

真实 RAG 必须显式确认并填写模型、知识库及规模：

```powershell
.venv\Scripts\python.exe scripts\benchmark_p7.py `
  --profile ai-real `
  --confirm-real-ai `
  --rag-mode-evidence <配置或部署证据> `
  --model <模型名> `
  --knowledge-base <知识库名> `
  --knowledge-base-size <文档或 chunk 数> `
  --output .tmp_tests\p7-benchmark\ai-real.json
```

本阶段未运行真实 AI 性能测试，因此报告和简历不得引用推测值。

## 4. 部署与稳定性验收

Compose 构建、启动、健康检查和端口暴露检查全部 `PASS`：

- Java liveness/readiness 为 `UP`；
- MySQL、Redis、Python AI 依赖状态均为 `UP`；
- 受保护的系统状态接口通过登录后 Bearer token 验证；
- 仅 Java `127.0.0.1:8080` 发布到宿主机；MySQL、Redis、Python AI 均未发布宿主机端口；
- Python 使用 fake RAG profile，避免把 stub 验收误写为真实模型验收。

证据：`.tmp_tests/p7-compose-final/summary.json`。

故障演练全部 `PASS`：

- Python AI 停止后 readiness 在约 1,865 ms 内转为 503，liveness 仍为 200；恢复后重新健康；
- Redis 停止后受保护接口 fail-closed，返回 503 / `AUTH_STATE_UNAVAILABLE`；
- MySQL 停止后业务写入约 4,591 ms 返回 503 / `DATASTORE_UNAVAILABLE`，并验证 `pythonCalled=false`，即 Java 业务写入失败前没有错误调用 Python；
- 所有依赖在演练结束后恢复健康。

## 5. 浏览器手动验收

使用 Codex 内置浏览器通过临时 HTTPS 隧道完成真实页面操作，结果 `PASS`：

1. 使用管理员账号登录，刷新后登录态保持；
2. 页面显示 `Java UP`、`Python AI UP`；
3. 新建会话 72 并发送中文问诊；
4. 响应展示 `ANSWERED / SUPPORTED / LOW / ALLOWED`；
5. 展示两条 RAG 引用及 `supervisor → livestock_rag_search → grounded_answer_agent → verifier_agent → safety_agent → response_agent` 工具链；
6. 刷新后会话、用户/助手消息和 `contextVersion=1` 均保持。

验收结束后已将 Java `CORS_ALLOWED_ORIGINS` 恢复为空、健康重建 Java 服务，并精确删除临时隧道容器；未删除或重建任何 named volume。

## 6. 自动化测试与发布入口

最终证据：

- Java：`mvnw.cmd -B -ntp clean verify`，127 tests，0 failures，0 errors，0 skipped；
- Python：611 passed，3 skipped；
- P7.2 新增安全/性能单元测试：PASS；
- JavaScript 语法、PowerShell parser、`git diff --check`：PASS；
- Compose 构建/健康/端口验收：PASS；
- Python、Redis、MySQL 故障演练：PASS；
- 源码和最终 Java/Python 镜像安全扫描：PASS；
- Codex 内置浏览器端到端验收：PASS。

统一入口：

```powershell
.\scripts\check_release_v7.ps1 -IncludePerformance
```

`-Skip*` 参数仅用于环境定位或快速检查；包含跳过项的摘要不能替代完整发布验收。标准 stub 性能 profile 各运行 5 分钟，因此必须用 `-IncludePerformance` 显式加入。

## 7. 最终判定

P7.2 的安全、性能、部署、韧性、自动化测试和浏览器验收均已完成，发布门禁判定为 **PASS**。真实 RAG/模型性能仍作为独立证据集管理，不影响本次 stub 发布结论，也不得在未实测前用于简历表述。
