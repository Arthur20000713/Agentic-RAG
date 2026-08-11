# P6 畜牧业务域与 SQLite→MySQL 迁移报告

日期：2026-08-06

分支：`codex/java-enterprise-integration`

## 1. 阶段目标与事实源边界

P6.3 将养殖场、动物档案和体尺测量记录从 Python 侧的历史 SQLite 业务表迁移到 Java/Spring Boot 管理的 MySQL 业务域。完成该阶段后，Java/MySQL 是 `farm`、`animal`、`measurement_record` 的唯一业务事实源；Python FastAPI 只接收 Java 已完成身份认证、权限检查和所有权校验后的动物快照、当前测量与有限历史，用于 Agent 编排和体尺分析。

本阶段不让 Python 读取或写入 MySQL 业务表，也不把一次“分析”隐式解释为“保存测量记录”。当前分析请求只返回 AI 结果；若后续需要记录本次测量，应增加独立、可审计的业务写接口。

## 2. Java/MySQL 畜牧业务域

Flyway `V7__livestock_domain.sql` 新增以下表：

- `farm`：以 `owner_id + farm_code` 唯一标识租户内养殖场。
- `animal`：以 `owner_id + animal_code` 唯一标识租户内动物，可关联同一 owner 的养殖场。
- `measurement_record`：保存动物历史体尺、测量日期、来源、置信度和算法版本等业务数据。

数据库层不只依赖应用代码维护隔离关系：`animal(farm_id, owner_id)` 复合外键指向 `farm(id, owner_id)`，`measurement_record(animal_id, owner_id)` 复合外键指向 `animal(id, owner_id)`，可阻止跨 owner 错绑。测量表还通过 CHECK 约束保证至少存在一个测量值、数值非负、置信度位于 0 到 1。

Java 暴露 `POST /api/v1/measurements/analyze`，要求 JWT、`MEASUREMENT_ANALYZE` 权限和格式合法的 `Idempotency-Key`。请求包含数据库动物 ID、六项可选但至少一项存在的当前测量值，以及可选置信度。VET 默认拥有该权限；普通 USER 不拥有。非 `TASK_MANAGE` 调用者只能读取自己的动物，越权访问统一返回 404，避免泄露资源是否存在；拥有 `TASK_MANAGE` 的管理角色可跨 owner 调用。

分析前，Java 从 MySQL 加载动物档案和最近 100 条历史记录，并按 oldest-to-newest 顺序发送给 Python。动物编号、species 缺失或出生日期非法时，在调用 AI 前返回 409。当前测量不会写入 `measurement_record`。成功后写入 `MEASUREMENT_ANALYZED` 审计事件，元数据包含内部 request ID、operation ID、outcome 和历史条数，不包含具体体尺数值。

## 3. Java→Python HTTP 合同与稳定性

Java 通过独立的 measurement HTTP client 调用 `POST /internal/v1/ai/measurements/analyze`，使用服务令牌、`X-Request-ID` 和 `Idempotency-Key`。业务请求中的用户 ID 与幂等键经 SHA-256 生成确定性的内部 request ID 和 operation ID，因此相同用户、相同幂等键在 Java 重启后仍保持稳定，避免 Python execution store 将重试识别为不同请求。

Compose 真实链路验收曾捕获一个定向 mock 未覆盖的序列化缺口：独立 `RestClient` 最初把 `LocalDate` 写成整数数组，Python 的 ISO 日期合同因此返回 422。`AiMeasurementRequest` 现已对动物出生日期和历史测量日期显式固定 `yyyy-MM-dd`，客户端测试也新增了出站 JSON 断言，防止跨语言日期格式再次漂移。

Python 侧按 operation ID、幂等键和 canonical request hash 认领或重放同步执行；相同标识绑定不同请求时返回 409。Java 对成功响应严格校验 header/body request ID、operation ID、run/trace ID、animal ID、outcome 和结果必填字段，并拒绝 `usedDemoHistory=true`。超时、服务不可用、上游协议错误、冲突和限流被映射为稳定的业务错误；measurement client 使用独立读超时，不与聊天或文档任务共用超时配置。

Python 根据输入返回 `ANALYZED`、`LOW_CONFIDENCE` 或 `INSUFFICIENT_DATA`。当前 payload deadline 为 10 秒，Java measurement client 的默认读取窗口为 15 秒，使 Python 有机会先返回结构化的 504，而不是由 Java 提前中断连接。

## 4. Python 业务数据边界

旧接口 `/api/measurement/analyze` 现在默认关闭，Compose 也显式设置 `legacy_api.measurement_enabled: false`；只有明确设置 `LEGACY_MEASUREMENT_API_ENABLED` 才能重新启用兼容入口。Java 使用的内部接口 `/internal/v1/ai/measurements/analyze` 保持启用，并由服务令牌保护。

边界测试对 Python 主连接和 execution store 连接安装 SQLite authorizer，拒绝读取、插入、更新或删除 `farm_profile`、`animal_profile`、`body_measurement_record` 及历史 memory 业务表；在该限制下，内部快照分析仍成功。这证明当前内部分析路径消费请求快照，不回读 Python 业务表。该测试是代码路径证据，不替代生产数据库账号最小权限配置。

## 5. SQLite→MySQL 离线迁移

迁移工具为 `scripts/migrate_p6_livestock_sqlite_to_mysql.py`，默认执行 dry-run；真正写入必须显式传入 `--apply`。迁移要求：

- 指定 legacy SQLite 源文件、精确 `--expected-sha256` 和明确的 `--target-owner-id`。
- apply 前提供独立的逐字节备份，并验证备份 SHA-256 与源一致；源文件以 read-only、immutable 模式打开并执行 `PRAGMA quick_check`。
- 校验三张旧表的必需列、业务 ID 格式、非空 species、ISO 日期、孤儿 farm/animal 引用、正整数 measurement ID、至少一个测量值、非负有限数值、DECIMAL 范围和 0–1 置信度；不为脏数据猜测默认值。
- 要求目标 owner 存在且为 `ENABLED`，并拒绝向非空的 P6 目标域执行全量导入。
- 使用 MySQL advisory lock 串行化迁移；写入前再次核对源与备份 hash，随后在单个数据库事务中导入 farm、animal 和 measurement。
- 在 `legacy_import_run` 保存迁移批次，在 `legacy_import_id_map` 保存 legacy ID 到 MySQL ID 的映射；提交前对账导入数量、映射数量、measurement 孤儿数和源文件 hash，失败则回滚。

迁移不会修改源 SQLite。由于工具采用“空目标域全量导入”模型，它不是在线增量同步器，也不会自动合并已存在的 MySQL 业务数据。

## 6. 已完成的定向验证

截至本报告编写时，已获得以下阶段性测试证据：

- Python 受影响测试：30/30 通过，包括旧 measurement API 默认关闭、Compose 配置关闭，以及内部快照路径不访问 Python 业务表。
- Java `PythonAiMeasurementClientTest`：3/3 通过，覆盖请求 header、成功合同校验、错配 operation ID 和结构化服务不可用错误。
- Java `P6LivestockIntegrationTest`：4/4 通过，使用真实 MySQL 8 与 Redis Testcontainers，覆盖最近 100 条历史顺序、不隐式保存 current、owner 404、USER 403、档案 409、数据库约束和审计事件。
- SQLite→MySQL 迁移 unit：6/6 通过，覆盖计划生成、dry-run、精确 hash、显式 owner、脏 species、空测量、独立备份和非法 owner。
- SQLite→MySQL 迁移 integration：2/2 通过，覆盖隔离 MySQL 中的完整导入/对账，以及非空目标域拒绝。
- Java 全量 `clean verify`：124/124 通过，包括真实 MySQL 8 与 Redis Testcontainers。
- Python 全量 pytest：606 passed、3 skipped；跳过项为测试套件既有条件跳过。
- 前端：Node 语法检查通过，`FrontendStaticContractTest` 4/4 通过；页面只调用 Java `/api/v1/measurements/analyze`，不出现 Python 内部地址。
- OpenAPI：business 19 paths、36 schemas、187 个本地 `$ref`；AI 9 paths、37 schemas、181 个本地 `$ref`；两者缺失引用均为 0。
- Python `compileall`、`git diff --check`：通过。当前环境未安装 Ruff，本报告不声称运行了 Ruff。
- Compose：Java、Python、MySQL、Redis 均 healthy，readiness 为 `UP`，Flyway V7 成功；MySQL、Redis、Python 未向宿主机暴露端口。
- Compose 真实 HTTP：VET 用户对 animal ID 1 返回 `ANALYZED`，刷新令牌轮换成功；分析前后 `measurement_record` 均为 3 条；最新 `MEASUREMENT_ANALYZED` 审计为 `SUCCESS`、`historyCount=3`，且审计 JSON 不含体尺值。
- 真实浏览器：在 Codex 应用内浏览器登录 VET 账号后，页面显示 Java `UP`、Python AI `UP`；打开“体尺分析”，提交 animal ID 1 的完整体尺与 `0.95` 采集置信度，页面返回 `ANALYZED`，并展示 summary、evidence、recommendation 和 report。刷新同一标签页后仍保持 VET 登录态，Java/Python 状态仍为 `UP`。
- 浏览器后数据库复核：animal ID 1 的 `measurement_record` 仍为 3 条；最新审计 ID 134 为 `MEASUREMENT_ANALYZED` / `SUCCESS`、`historyCount=3`，且 `detail_json` 不包含体高、体长、胸围、胸深、胸宽、体重或置信度字段。

以上结果覆盖本轮 P6 自动化与 Compose 后端门禁。Python 全量首轮曾在 Windows Torch DLL 加载时发生进程级访问冲突；随后独立完整复跑到 100% 并得到 606 passed、3 skipped，因此以成功完整复跑作为门禁证据。

## 7. FAKE/REAL 边界与浏览器验收状态

默认 Compose 的 `rag_server.query_mode` 仍为 `fake`。这意味着可以验证 Java/MySQL 业务闭环、鉴权、幂等、HTTP 合同、Python Agent 路径、任务恢复和跨服务部署，但不能把 FAKE 文档 ingestion 或 FAKE RAG 查询描述为真实向量检索已经投产。REAL RAG 仍依赖固定并容器化 sibling RAG-SERVER 制品、索引卷映射和真实检索回查。

体尺分析前端、business OpenAPI、Compose 后端链路、数据库副作用和脱敏审计均已完成验证。真实浏览器手动验收也已通过：VET 登录、运行状态、体尺弹窗、AI 提交、`ANALYZED` 结果展示以及刷新后的登录态均得到页面证据；浏览器触发分析后又通过 MySQL 复核了“不隐式保存 current”和审计不记录体尺值两项边界。

至此 P6.3 的实现、自动化门禁、Compose 真实 HTTP、真实浏览器和数据库副作用验收全部完成。验收使用的临时 8088 代理只服务于浏览器访问，完成后删除并确认端口关闭；MySQL、Redis 和 Python 仍未向宿主机暴露端口，也未删除任何 Compose named volume。

真实外部模型或 REAL RAG-SERVER 的生产级端到端验收仍不在本阶段已完成范围内。当前可确认的是：Java/MySQL 畜牧业务事实源、Java→Python 授权快照边界、可审计离线迁移、前端业务入口、完整自动化门禁和 Compose 后端链路均已落地并通过对应验证。
