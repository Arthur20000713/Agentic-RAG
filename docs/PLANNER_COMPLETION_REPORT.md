# Planner + Executor + Verifier + Replan 完成报告

## 1. 验收结论

阶段二 P0–P6 已完成开发、审核、分层测试和系统验收。`general_qa` 与
`disease_consultation` 现在通过受控计划执行；简单回答、越界问题和结构化体尺分析继续使用固定路径。

最终 chat 拓扑为：

```text
context -> memory_search -> router
  complex -> planner -> executor -> plan_verifier
  plan_verifier -> executor | replan | verifier
  replan -> executor | verifier
  direct -> verifier
  verifier -> safety -> final -> memory_write -> END
```

阶段二严格限制为最多一次知识检索。query decomposition、query rewrite、evidence grading 和受控二次检索属于阶段三，不在本阶段提前实现。

## 2. 交付能力

- `TaskPlan`、`PlanStep`、执行结果、失败、校验和重规划记录均为可 checkpoint 的 Pydantic schema。
- Planner 输出经过 action allowlist、参数、步骤数和 DAG 校验；非法计划在 Executor 零调用时关闭。
- Executor 按依赖串行执行，使用稳定 operation key，并受单步骤尝试次数和总执行次数限制。
- `PlanVerifier` 独立校验步骤输出与总体目标；最终 `VerifierAgent` 和 `SafetyAgent` 保持原职责。
- 瞬时错误先原步骤重试一次；持续可恢复错误增加 revision，保留完成步骤并切换到安全 fallback；永久环境错误不重试、不重规划。
- SQLite checkpoint 可在关闭并重开 saver 后通过 `ainvoke(None, config)` 真实续跑，已完成的检索步骤不会重复。
- 新 turn 使用显式 reset 标记清空计划、工具、答案、安全和错误等瞬态字段；resume 不触发 reset。
- chat debug 与 trace API 只暴露 plan ID、revision、步骤计数、决策和终止码等摘要，不包含 prompt、思维链、Memory 内容或完整工具 payload。
- Memory 读取仍在 Planner 前，不能充当检索证据；Memory 写入仍在 Final 后，Planner 和 Replan 均不能调用。

## 3. 系统验收矩阵

| 场景 | 结果 |
|---|---|
| 正常两步知识问答 | 1 次检索、2 次步骤执行、goal 通过 |
| 一次瞬时失败 | 原步骤重试成功，不计为 replan |
| 持续瞬时失败 | 2 次检索后 revision 变为 2，执行一次安全 fallback |
| 永久环境失败 | 1 次检索后 terminal，终止码保留且无引用 |
| Safety 阻断 | 不出现 `safety -> replan`，具体剂量从最终回答移除 |
| 循环上限 | 持续失败在固定调用次数内终止，无无限循环 |
| SQLite 重启续跑 | 已完成 retrieval 不重复，只继续 compose |
| 同 thread 新 turn | 不继承 plan、结果、错误、RAG 上下文或旧答案 |
| Memory 边界 | 跨会话召回可用，但不进入 sources/citations，写入只发生在 Final 后 |

## 4. 验证证据

所有提交门禁均在由 staged tree 创建的独立 worktree 中运行，未使用根工作区已有未提交改动。

### P5 精确门禁

```text
113 passed, 1 warning
```

覆盖 checkpoint、planning schema、Planner、Executor、Replan、API debug/trace、internal-v1、Memory graph 和 LangGraph workflow。

### P6 系统验收

```text
13 passed, 1 warning
```

覆盖新增 Planner 系统场景、长期 Memory 重启场景、Memory 安全写入和疾病 Safety 场景。

### 全量离线回归

```text
670 passed, 3 deselected, 1 warning
```

执行命令：

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server" `
  --ignore=tests/integration/test_p4_sqlite_mysql_migration.py `
  --ignore=tests/integration/test_p6_livestock_sqlite_mysql_migration.py `
  -q -p no:cacheprovider
```

本机缓存的 `Qwen/Qwen2.5-0.5B-Instruct` 可选 smoke 同时通过：42 项本地模型单元测试通过，transformers smoke 返回 `PASSED`。

## 5. 审核发现与修复

- 全量回归发现 multi-agent evaluator 仍硬编码旧固定 agent path，已更新为 Planner/Executor/PlanVerifier 路径。
- 预加载 fake tokenizer/model 的 Transformers 单测不应强制导入可选运行时，导入现在只发生在真正加载模型时。
- 根工作区已有真实 RAG、疾病上下文、Java 和配置改动未进入本阶段提交；冲突文件使用精确 index staging。

## 6. 环境限制和剩余风险

- Docker Desktop Linux engine 当前不可用，两个 SQLite/MySQL 迁移测试未执行，不能记为通过。错误为 Linux engine named pipe 不存在。
- 真实 RAG-SERVER 质量门禁未纳入阶段二离线回归；阶段三 Agentic Retrieval 必须单独运行并记录真实语料结果。
- Starlette 对当前 TestClient/httpx 组合产生一条弃用警告，不影响本阶段行为。
- 本阶段 Replan 是受控、可审计的失败链替换，不做开放式工具生成；检索替代策略将在阶段三加入。

## 7. 提交记录

| 小任务 | Commit |
|---|---|
| P0 DEV_SPEC | `da01b3b` |
| P1 Planning schema | `7055a97` |
| P2 TaskPlanner + Supervisor | `4a71a2e` |
| P3 Executor + PlanVerifier | `d9eef86` |
| P4 Replan + LangGraph 拓扑 | `a20567d` |
| P5 Checkpoint + 可观测性 | `9d11010` |
| P6 系统验收与本报告 | 本次提交 |
