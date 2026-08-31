# Agentic RAG 能力升级 DEV_SPEC

## 1. 目标与顺序

本轮升级严格按以下顺序交付，前一项完成开发、审核、分层测试和系统验收后，才进入下一项：

1. 长期记忆：Checkpointer、Store、`search_memory`、`write_memory`。
2. Planner + Executor + Verifier + Replan。
3. Agentic Retrieval：query decomposition、query rewrite、evidence grading、二次检索。
4. Model Router：本地小模型执行 intent/slot/risk，大模型执行 planning/reasoning，并评测 task success、latency、tokens、cost。

每个小任务必须满足：最小实现、目标测试通过、审核 staged diff、独立 commit、push 到当前跟踪分支。禁止把工作区已有未提交改动夹带进 commit。

## 2. 全局工程约束

- 使用项目根目录 `.venv\Scripts\python.exe` 执行 Python 和 pytest。
- 默认测试不得调用外部模型或真实 RAG；使用 fake client 和临时 SQLite 文件。
- LangGraph 状态只保存可序列化数据，数据库连接、模型客户端和 Store 放在 runtime/context。
- Java/MySQL 继续作为动物主档和业务事实权威。Python 长期记忆只保存授权快照、用户确认事实、工具结果和历史咨询上下文。
- `ai_inferred`、诊断、风险结论、治疗建议和 RAG 摘要不得写入长期记忆。
- Memory 只能补充上下文，不能覆盖本轮用户显式输入，不能替代 RAG citation、Verifier 或 Safety。
- 所有跨用户数据按 `user_id` 隔离；同名 `animal_id` 不得跨用户检索。
- 功能开关关闭时保持现有行为，不产生数据库副作用。

## 3. 阶段一：长期记忆 Memory

### 3.1 当前基线与缺口

仓库已有 `MemoryService.maybe_write_memory`、append-only `memory_event`、`animal_memory/farm_memory` 投影及写入测试。现有能力仍有以下缺口：

- LangGraph 未绑定 Checkpointer 或 Store，调用未传 `configurable.thread_id`。
- 没有 `search_memory` / `write_memory` 工具接口。
- `read_enabled` 未被消费，正式 Chat 和 internal-v1 路径没有跨会话读取。
- 现有 projection 只按 animal/farm ID 建键，不能直接用于多租户读取。
- `ttl_days` 没有进入可查询的事实 envelope。

### 3.2 设计边界

#### Checkpointer

- `thread_id = user_id:session_id`，只负责同一用户、同一会话内的工作流 checkpoint、恢复和状态历史。
- 使用独立 SQLite checkpoint 存储，不与长期事实的事件语义混用。
- 每轮必须重置瞬态字段，防止上一轮的 `final_answer`、tool result、error 或 safety 状态泄漏到下一轮。

#### Store

- 实现 LangGraph `BaseStore` 兼容适配器，复用现有 SQLite MemoryRepository 的 append-only 事件和 projection，不建立第二套长期事实真相源。
- namespace 采用 `("memory", user_id, "animal", animal_id)`；只有同一 `user_id + animal_id` 可以读取。
- Store item 保存完整 envelope：record ID、memory type、content、source、session ID、created/updated/expires 时间和来源元数据。
- 动物档案使用稳定 key 更新；历史咨询使用独立 key 追加，保留时间线。

#### Tools

- `write_memory` 只接受 `user_confirmed` 或 `tool_result`，拒绝 AI 推断、诊断、风险和建议类内容。
- `search_memory` 按 namespace、类型、关键词、TTL 和 limit 返回稳定排序结果。
- 工具调用结果写入 `state.tool_results`，用于 trace/debug；不得把内部 SQL 或未过滤 payload 返回给用户。

### 3.3 小任务与提交门禁

| 编号 | 小任务 | 主要产物 | 目标验证 | 状态 |
|---|---|---|---|---|
| M0 | 审计与规范 | 本 DEV_SPEC、基线测试记录、安全/数据所有权决策 | 现有 Memory 相关离线测试通过；`git diff --check` | 已完成 |
| M1 | Checkpointer 基础 | SQLite saver 生命周期、graph compile 注入、`session_id -> thread_id` | 同线程恢复、异线程隔离、瞬态字段不泄漏 | 已完成 |
| M2 | Store 适配器 | Repository-backed `BaseStore`、租户 namespace、TTL envelope | put/get/search/delete、跨用户隔离、关闭重开后仍可读 | 已完成 |
| M3 | Memory tools | `search_memory`、`write_memory`、来源/类型安全校验 | 允许来源、拒绝来源、幂等/更新、查询与过期过滤 | 已完成 |
| M4 | 正式路径接线 | Memory 节点、ChatService、`/api/chat`、internal-v1、功能开关 | session A 写入，session B 读取；tools/trace 可见；关闭开关无副作用 | 已完成 |
| M5 | 系统验收与审核 | 重启 E2E、安全负例、回归结果、完成报告 | 跨 App 重启、跨用户隔离、冲突优先级、全量非真实 RAG 回归 | 已完成 |

每个小任务遵循 TDD：先补失败测试，再写最小实现，运行目标测试，检查 diff，commit 并 push。

### 3.4 Memory 验收标准

#### 单元测试

- Checkpointer 同 `thread_id` 可恢复，不同 `thread_id` 隔离。
- Store namespace 严格隔离 user/animal，支持稳定排序、limit、query/type 过滤和 TTL。
- `write_memory` 拒绝 `ai_inferred`、诊断、建议及缺失主体的输入。
- `search_memory` 在读取开关关闭时不访问 Store。
- 本轮显式事实与历史记忆冲突时，本轮事实优先。

#### 集成测试

- graph 显式绑定 checkpointer/store，invoke 传入 `configurable.thread_id`。
- 同用户同动物跨 session 可检索，另一用户或另一动物不可检索。
- profile 更新形成 append-only supersede 事件；咨询记录按 turn 追加。
- 删除后不可检索，历史事件仍可审计。
- Store 关闭连接并从同一临时 SQLite 文件重开后仍能读取。

#### 系统测试

1. App 实例 A：session A 写入授权动物档案和用户确认咨询事实。
2. 关闭实例 A，使用相同数据库启动 App 实例 B。
3. 同一用户、同一动物、session B 查询时命中 Memory，并在 tools/trace 中显示 `search_memory`。
4. 使用另一用户、另一动物和 `read_enabled=false` 分别验证不命中。
5. 验证 Memory 不会绕过疾病回答的 RAG、Verifier 和 Safety。

### 3.5 Memory 测试命令

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_checkpointing.py tests/unit/test_memory_service.py tests/unit/test_memory_store.py tests/unit/test_memory_tools.py tests/integration/test_memory_schema.py tests/integration/test_memory_repository.py tests/integration/test_memory_store_persistence.py tests/integration/test_memory_graph.py tests/integration/test_memory_internal_api.py tests/e2e/test_memory_flow.py tests/e2e/test_long_term_memory_system.py -q -p no:cacheprovider
.venv\Scripts\python.exe -m pytest -m "not rag_server" --ignore=tests/integration/test_p4_sqlite_mysql_migration.py --ignore=tests/integration/test_p6_livestock_sqlite_mysql_migration.py -q -p no:cacheprovider
```

阶段完成记录见 `docs/MEMORY_COMPLETION_REPORT.md`。两项 MySQL 迁移测试只有在 Docker Desktop Linux engine 可用时单独执行，不得将环境跳过记录为通过。

## 4. 阶段二：Planner + Executor + Verifier + Replan

Memory 完成后补充该阶段的详细设计评审，当前先锁定最小验收边界：

- Planner 输出受 schema 约束的目标、步骤、依赖、工具和完成条件。
- Executor 每次只执行当前可运行步骤，所有工具仍经过 allowlist 和参数校验。
- Verifier 对步骤结果和总体目标分别判定，返回结构化失败原因。
- 可恢复失败进入 Replan，携带已完成步骤和失败证据；设置最大重规划次数，防止死循环。
- 覆盖成功、工具失败后重规划、不可恢复失败、安全阻断和循环上限测试。

## 5. 阶段三：Agentic Retrieval

Planner 阶段完成后细化，最小验收边界如下：

- 复杂问题可拆成有限个子查询，并保留原始问题。
- query rewrite 不改变关键实体、动物、时间和否定语义。
- evidence grader 对相关性、覆盖度、来源质量和冲突给出结构化结果。
- 证据不足时允许一次受控二次检索，记录触发原因和改写查询。
- 达到次数上限仍不足时进入 no-answer/追问，不编造答案。

## 6. 阶段四：Model Router 与评测

Agentic Retrieval 完成后细化，最小验收边界如下：

- 本地小模型候选任务仅限 intent、slot、risk 等低成本结构化判断。
- planning/reasoning 使用能力更强的主模型；安全策略可以强制升级模型。
- 路由失败可回退，记录 selected model、fallback reason、latency、tokens 和估算 cost。
- 以固定 golden set 比较 router on/off 的 task success、P50/P95 latency、tokens 和 cost。
- 只有 task success 不低于基线且安全集不退化，才允许默认启用。

## 7. 最终完成定义

- 四项功能严格按顺序完成，每项均有独立完成报告和可追溯 commits。
- 所有新增路径有单元、集成和系统测试；外部依赖不可用时不得伪造通过。
- 默认离线全量回归通过，真实 RAG/模型测试单独报告环境与结果。
- 最终审核确认无跨用户记忆泄漏、无限循环、无证据回答、静默模型降级或敏感配置泄漏。
