# 长期记忆 Memory 完成报告

## 1. 交付结论

截至 2026-08-31，DEV_SPEC 的 M0–M5 已按顺序完成。系统具备持久化 LangGraph Checkpointer、Repository-backed Store、安全的 `search_memory`/`write_memory`、跨会话动物档案与历史咨询读取，以及应用重启后的恢复能力。

长期记忆默认关闭，由 `long_term_memory.read_enabled` 和 `long_term_memory.write_enabled` 独立控制。Java/MySQL 仍是动物业务档案权威；Python Memory 只保存授权快照、用户确认事实、工具结果与咨询历史。

## 2. 架构与边界

- Checkpointer 使用独立 SQLite 文件，`thread_id` 由 `user_id + session_id` 无歧义编码，只恢复同一用户会话的工作流状态。
- Store 复用现有 `memory_event` 事件流及 animal/farm projection，不建立第二套事实源。
- namespace 为 `("memory", user_id, subject_type, subject_id)`；搜索、读取、更新和删除均受用户与主体隔离。
- animal profile 使用稳定 key 更新并保留 supersede 事件；consultation 按 operation/turn 追加。
- internal-v1 只有在 Java 提供可信 `AnimalSnapshot` 时启用动物长期记忆。
- legacy `/api/chat` 接入 Checkpointer，但因缺少可信动物所有权证明，不读取或写入动物长期记忆。

## 3. 安全约束

`write_memory` 仅接受 `user_confirmed` 和 `tool_result`。以下内容会被拒绝：

- `ai_inferred`；
- 诊断、风险分级、治疗、用药或建议；
- 最终回答、RAG 摘要及其他模型生成结论；
- 缺失用户或主体作用域的数据。

Memory 只补充上下文。本轮用户显式事实优先；Memory 不进入 citations，不替代 RAG 证据、Verifier 或 Safety，也不能将当前低风险事实升级为高风险结论。

## 4. 提交记录

| 阶段 | Commit | 内容 |
|---|---|---|
| M0 | `4224a5b` | DEV_SPEC、数据所有权与安全边界 |
| M1 | `187b29e` | 持久化 SQLite Checkpointer |
| M2 | `e2fe288` | Repository-backed LangGraph Store |
| M3 | `43e65aa` | 安全的 Memory 读写工具 |
| M4 | `c937b43` | graph、ChatService、internal-v1 与应用生命周期接线 |
| M5 | 本报告所在提交 | 重启系统测试、全量回归与阶段冻结 |

## 5. 验证结果

验证在只包含 HEAD 与 M5 staged 内容的隔离 worktree 中执行，避免工作区既有未提交改动影响结果。

| 范围 | 结果 |
|---|---|
| Checkpointer、Store、tools、graph、internal-v1、Memory E2E | `34 passed` |
| 全量离线回归，排除真实 RAG marker 与两项 Docker/MySQL 迁移文件 | `630 passed, 3 deselected` |
| staged whitespace 检查 | 通过 |

系统测试验证了：App A 写入后 App B 可读取；checkpoint 表实际持久化；同一用户/动物可跨 session 召回；不同用户隔离；关闭读写开关无副作用；Memory 不进入 sources/citations；历史症状不会覆盖本轮否定事实并升级为 `HIGH/CRITICAL`。

## 6. 环境限制与后续门禁

本机 Docker CLI 可用，但 Docker Desktop Linux engine 不可用，因此以下测试未执行，不能记录为通过：

- `tests/integration/test_p4_sqlite_mysql_migration.py`
- `tests/integration/test_p6_livestock_sqlite_mysql_migration.py`

它们属于既有 SQLite→MySQL 迁移验证，并非 Memory 代码路径。Docker/MySQL 环境恢复后应单独补跑。真实 RAG/外部模型测试也保持独立，不纳入本次离线验收。

Memory 阶段至此冻结。下一阶段必须先细化 Planner + Executor + Verifier + Replan 的 DEV_SPEC，再开始实现。
