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

### 4.1 当前基线与改造范围

当前 `SupervisorAgent` 只做意图分类；`_planner_node` 只生成一个固定的 `query_knowledge_hub` 调用；`tool` 节点失败时只用相同参数重试。现有 `VerifierAgent` 验证最终回答、引用和安全约束，不验证计划步骤或总体目标。

阶段二只改造 `general_qa` 与 `disease_consultation`。`assistant_intro`、`out_of_scope` 和结构化 `measurement_analysis` 保持固定路径，避免无意义的规划延迟。阶段二每个计划最多包含一次知识检索；query decomposition、query rewrite、evidence grading 和二次检索留到阶段三。

### 4.2 状态与 Schema

新增 checkpoint-safe Pydantic 模型：

- `PlanStep`：`step_id`、action、description、dependencies、arguments、completion criteria。
- `TaskPlan`：`plan_id`、goal、steps、overall criteria、source 和 revision。
- `StepExecutionResult`：step、status、output reference、error、retryable 和 attempt；只引用 `tool_results`，不复制大段 RAG payload。
- `ExecutionFailure`：失败类别、稳定错误码、step、可恢复性和原因。
- `ReplanRecord`：revision、触发错误、保留的完成步骤和替换步骤。

`MultiAgentState` 保存计划、当前步骤、步骤结果、失败、执行次数、重规划次数和历史。模型客户端、工具函数、数据库连接仍只存在于 runtime。旧 `tool_plan/tool_attempt` 在阶段二保留为兼容投影，完成迁移后再单独评估删除。

### 4.3 Planner、Executor、Verifier 与 Replan

- `TaskPlanner` 只接收最小结构化上下文，主模型仅返回 schema 约束 JSON；模型不可用或输出非法时使用服务端确定性 fallback。所有计划在执行前必须经过 schema、DAG、action allowlist 和参数验证。
- action allowlist 限于无副作用内部动作：`understand_disease`、`query_knowledge_hub`、`compose_grounded_answer`、`safe_fallback`。禁止反射调用任意函数或执行用户提供的 tool JSON。
- `ExecutorAgent` 串行选择依赖已完成的第一个 pending step。阶段二不实现并行执行。
- `PlanVerifier` 独立于最终 `VerifierAgent`：前者验证步骤输出和总体目标，后者继续验证最终回答、citation 和 grounding。
- `ReplanAgent` 接收已完成步骤与失败摘要，保留成功结果，只替换未完成或失败步骤。相同参数重试只算 retry；revision 增加且步骤发生变化才算 replan。
- Memory search 仍在 Planner 前提供上下文，但不能成为 evidence/citation；`memory_write` 仍在 Final 后，不能成为 Executor step。
- Safety 是不可绕过的终点门禁。禁止任何 `safety -> replan` 边。

推荐 chat 拓扑：

```text
context -> memory_search -> router
  complex -> planner -> executor -> plan_verifier
  plan_verifier -> executor | replan | verifier
  replan -> executor | verifier
  direct -> verifier
  verifier -> safety -> final -> memory_write -> END
```

### 4.4 失败分类与循环上限

| 类别 | 例子 | 行为 |
|---|---|---|
| 可恢复执行失败 | RAG timeout、瞬时 MCP/internal error、reasoning draft/schema 缺失 | 在预算内 replan，保留已完成步骤 |
| 证据不足 | empty、low confidence | 阶段二直接 no-answer/追问，不进行二次检索 |
| 不可恢复计划失败 | schema/DAG/allowlist/参数错误、依赖环、无 runnable step | Executor 零调用，fail closed |
| 不可恢复环境失败 | RAG path/collection 缺失、受信输入缺失 | 安全失败答复，不用 fake client 降级 |
| 安全阻断 | dosage、prescription、definitive diagnosis 等 | 直接进入 Safety/Final，禁止 replan |
| deadline/cancellation | internal-v1 deadline、任务取消 | 向上传播，不包装成可重试工具错误 |

服务端硬限制：`max_plan_steps=3`、`max_replans=2`、`max_step_attempts=2`、`max_total_step_executions=8`。达到任一上限后以稳定终止码结束并返回无证据安全答复；LangGraph recursion limit 只作为最后保险。

### 4.5 Checkpoint、幂等与可观测性

- 每个执行步骤使用稳定 operation key：`request_id + plan_id + step_id + attempt`。
- 同一中断 run 从 SQLite checkpoint 恢复时，不重复已完成步骤；必须用 `ainvoke(None, config)` 或受控 `Command(resume=...)` 验证真实 resume，不能重新提交完整 state 冒充恢复。
- 同一 thread 的新 request 必须清空 plan、current step、results、failure 和 replan history；以 `request_id` 区分 resume 与新 turn。
- trace 记录 planner/executor/plan_verifier/replan 的 plan revision、step、attempt、decision、error code 和 latency；不记录 chain-of-thought、完整 prompt、密钥或大段工具 payload。
- legacy 与 internal-v1 的外部 response contract 保持不变；规划摘要先进入现有 debug/trace。

### 4.6 小任务与提交门禁

| 编号 | 小任务 | 主要产物 | 目标验证 | 状态 |
|---|---|---|---|---|
| P0 | 审计与规范 | 本阶段 DEV_SPEC、状态/失败/边界决策 | Planner 相关基线通过；`git diff --check` | 已完成 |
| P1 | Planning schema 与校验器 | Pydantic schema、DAG/allowlist/limit validator | 合法计划；duplicate/missing/cycle/unknown/超限均拒绝 | 已完成 |
| P2 | TaskPlanner 与 Supervisor 协调 | 主模型 schema 输出、确定性 fallback、plan trace | general 两步、disease 三步；非法模型输出不执行 | 已完成 |
| P3 | Executor 与 PlanVerifier | 串行依赖调度、结果契约、step/goal 判定 | 依赖顺序、输出缺失、永久失败、deadlock | 已完成 |
| P4 | Replan 与 LangGraph 拓扑 | 条件边、失败分类、保留成功步骤、循环上限 | 一次失败后改计划成功；安全/永久失败不循环 | 已完成 |
| P5 | Checkpoint 与可观测性 | resume API、新 turn reset、trace/debug 摘要 | 重启续跑不重复步骤；同 thread 新请求无状态泄漏 | 已完成 |
| P6 | 系统验收与审核 | scripted E2E、回归结果、完成报告 | 成功/重规划/失败/安全/上限/Memory 边界与全量离线回归 | 未开始 |

每个小任务先补失败测试，再写最小实现，运行目标回归，审核 staged diff，独立 commit 并 push。

### 4.7 阶段验收标准

- 简单路径输出、citation、risk 和 Safety 行为与当前版本兼容。
- complex plan 的 step ID 唯一、依赖无环、只使用 action/tool allowlist。
- recoverable failure 触发 revision 增加的真实 replan，完成步骤不重跑，恢复成功后旧错误归档而不污染最终状态。
- invalid/permanent/safety/deadline 路径分别按策略结束，Executor 调用数和终止码可断言。
- 三种无限循环输入在 `asyncio.wait_for` 内按服务端预算终止。
- Checkpointer 可跨连接恢复未完成计划；不同用户仍隔离；新 turn 不继承旧计划瞬态字段。
- Memory 不进入 retrieved evidence/citations，replan 不重复 `write_memory`。

P0 基线命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_langgraph_topology.py tests/unit/test_verifier_agent.py tests/unit/test_checkpointing.py tests/integration/test_langgraph_workflow.py tests/integration/test_tool_timeout.py -q -p no:cacheprovider
```

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
