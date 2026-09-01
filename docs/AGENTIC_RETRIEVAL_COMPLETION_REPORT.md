# Agentic Retrieval 完成报告

## 1. 验收结论

阶段三 R0–R7 已按顺序完成开发、审核、分层测试和系统验收。`general_qa` 与
`disease_consultation` 的单次检索 action 现在内部执行有界检索微流程：最多三个主查询，证据不足时
最多生成一个受语义约束保护的二次查询，总语义 RAG 调用不超过四次。

离线功能、回归和 Fake golden set 均通过。真实 RAG adapter smoke 通过，但严格质量门禁没有通过：
目标 collection `livestock_v4_2` 在当前 RAG-SERVER 中不存在，`batch_002` 的十个本地语料文件也
全部缺失。真实评测因此以 `RAG_COLLECTION_NOT_FOUND` 生成 `status=skipped` 工件；本报告不把它
记为成功，也不使用历史 80/80 快照替代本次回归。

## 2. 交付能力与边界

- 查询分解输出 1–3 个只读主查询；模型不可用、超时、非法 JSON 或语义校验失败时使用确定性回退。
- rewrite 只针对 grader 的缺失方面生成一次 secondary query，并保留动物、实体、数字、单位、
  时间和否定语义；不安全改写会被拒绝且不调用 RAG。
- 聚合按稳定 evidence key 去重，保留来源 URI、正文和 citation 映射；grader 独立记录相关性、覆盖、
  来源质量、缺失方面、冲突和服务端最终决策。
- 二次检索后仍不足或冲突未解时返回结构化 no-answer，清空 hits、citations、retrieved contexts 和
  sources，不调用 reference-only 模型生成结论，也不触发 Planner Replan。
- 所有调用均失败且没有证据时，才保持阶段二的 retry/replan 失败语义；部分基础设施失败但有效证据
  足够时允许有记录地完成。
- checkpoint 保存查询、attempt、grade、调用数和最终投影；完成 action 后 resume 不重复检索，
  同 thread 新 turn 清空检索瞬态状态。
- S4 和规则可确定的 no-answer 在 decomposition 前阻断，`rag_call_count=0`。Safety 使用原始用户输入，
  最终图固定经过 `Verifier -> Safety -> Final`，无 Safety 回边。
- 长期 Memory 不进入 intent/disease 模型检索上下文、aggregate hits、grade、citation 或 sources。
- internal-v1 与 legacy 外部响应结构保持不变；legacy 非 Agentic empty/reference-only 行为仍有精确测试。

## 3. 系统验收矩阵

| 场景 | 可验证结果 |
|---|---|
| 单问题证据充分 | 1 次主检索，`final_status=sufficient`，返回 grounded sources |
| 可拆问题证据充分 | 2 个模型分解查询，2 次检索，聚合去重后回答 |
| 最大调用预算 | 3 个主查询均 empty，1 个 secondary 成功，严格 4 次调用 |
| rewrite 拒绝 | 语义漂移改写不执行 secondary，调用数不增加 |
| 二检仍不足 | `final_status=insufficient`，无 hits、citations、sources 或 Replan |
| 冲突未解决 | 二检后仍 no-answer，只提示人工复核，不输出结论或 citation |
| 部分基础设施失败 | 记录 error attempt；其余证据满足阈值时可完成 |
| Safety 前置阻断 | S4/规则拒答在 decomposition 前结束，RAG 调用为 0 |
| Checkpoint resume | 已完成 retrieval action 不重跑 |
| 同 thread 新 turn | query、attempt、grade、计数和旧答案全部清理 |
| Memory 隔离 | Memory 可提供背景，但不进入检索 query、证据或引用 |
| 协议兼容 | internal-v1、legacy chat 与旧非 Agentic 路径回归通过 |

## 4. 验证证据

测试在只包含提交基线与 R7 变更的隔离 worktree 中运行，Python 版本为 3.12.7。

### 4.1 Scripted 完整图 E2E

```text
tests/e2e/test_agentic_retrieval_system.py
3 passed
```

三条用例分别覆盖模型 decomposition、三主加一 secondary 的四调用上限，以及冲突二检后 no-answer。

### 4.2 精确 Agentic Retrieval 矩阵

```text
112 passed, 1 warning
```

覆盖 retrieval schema、decomposition/rewrite、evidence grading、orchestrator、grounded answer、图拓扑、
checkpoint/new turn、Memory graph、internal-v1 和完整图 E2E。

### 4.3 Fake golden set

```text
total_cases=60
passed_cases=60
pass_rate=1.0
intent_accuracy=1.0
rag_call_accuracy=1.0
citation_coverage=1.0
no_answer_accuracy=1.0
safety_pass_rate=1.0
follow_up_accuracy=1.0
structure_completeness=1.0
rag_citation_coverage=0.9
source_uri_coverage=0.9
```

Fake 评测用于业务回归，不替代 scripted Agentic 功能矩阵或真实 RAG 质量门禁。

### 4.4 全量离线回归

```text
718 passed, 3 deselected, 1 warning
```

执行命令：

```powershell
.venv\Scripts\python.exe -m pytest tests -m "not rag_server" `
  --ignore=tests/integration/test_p4_sqlite_mysql_migration.py `
  --ignore=tests/integration/test_p6_livestock_sqlite_mysql_migration.py `
  -q -p no:cacheprovider
```

两项 Docker/MySQL 迁移文件依赖本机不可用的 Docker Linux engine，故单独排除，不能记录为通过。
三项 `rag_server` marker 测试单列运行结果为 `3 passed, 721 deselected`；它们只证明 CLI dry-run、
MCP tools/list 与 adapter 连接，不证明目标 collection 的检索质量。

## 5. 真实 RAG 严格门禁

### 5.1 环境快照

| 项目 | 当前证据 |
|---|---|
| Agentic RAG commit | `70be00d` 加本次 R7 staged 变更 |
| RAG-SERVER 路径 | `C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER` |
| RAG-SERVER commit | `9ef84c3`，工作区有未提交改动 |
| 目标 collection | `livestock_v4_2` |
| 实际 collections | `default`、`knowledge_hub`、`raw_txt_ollama`、若干 smoke/e2e collection；无目标 collection |
| batch | `batch_002`，状态 `planned` |
| batch 本地文件 | 十个 `C:\tmp\livestock_corpus\batch_002\*.md` 全部缺失 |
| embedding 依赖 | 当前默认使用 Ollama；本机无 Ollama 进程或 11434 listener |

RAG-SERVER 工作区是可变的 sibling repository，因此 commit 和 dirty 状态一并记录，避免把当前结果误解为
可复现的固定基线。

### 5.2 实际结果

真实评测命令使用 `mode=real`、目标 batch、真实 golden set 和 `optional` 仅用于保存阻断工件。结果为：

```text
status=skipped
mode=real
error_code=RAG_COLLECTION_NOT_FOUND
reason=target collection not found: livestock_v4_2
```

当前 worktree 工件位于 `.tmp_tests/agentic_retrieval_real_r7/`，包括
`real_rag_preflight.json`、`eval_result.json`、CSV、summary 和 failure analysis。

严格 gate 随后执行并以退出码 1 失败：

```text
Quality gate: failed
- real eval skipped: RAG_COLLECTION_NOT_FOUND - target collection not found: livestock_v4_2
```

`check_rag_corpus.py --require-files` 同样以退出码 1 报告十个源文件缺失。因此本阶段的真实 RAG 结论是
“门禁已执行并被外部数据环境阻断”，不是“质量通过”。恢复 collection、语料文件和 Ollama 后，应重新运行
不接受 skipped 的最终 gate；只有 `eval_result.json` 为真实非 skipped 结果且 `check_v4_2 --stage gate`
退出码为 0，才可宣称通过。

## 6. 审核发现与修复

- 完整图系统测试补上了此前只在单元/集成层覆盖的模型 decomposition、四调用上限和冲突 no-answer。
- 旧 document-QA E2E 查询会被新的领域边界提前阻断；测试输入改为畜牧领域 empty 查询，并明确断言
  两次有界检索、`insufficient` 和无引用。
- golden evaluator 的旧断言仍把合成 citation 计为 0；现按 canonical Agentic 投影记录为 1，同时保留
  `RAG_CITATION_SYNTHESIZED_FROM_HIT` warning，避免观测字段与实际回答不一致。
- 两轮 R6 staged review 发现的英文 no-answer、partial source warning 和 Safety 路由问题已在 R6 修复，
  R7 回归继续覆盖这些边界。

## 7. 提交记录

| 小任务 | Commit |
|---|---|
| R0 DEV_SPEC | `9d4370e` |
| R1 Retrieval schema | `89aada1` |
| R2 Decomposition + rewrite | `4cbba98` |
| R3 Aggregate + grader | `173289d` |
| R4 Orchestrator | `cd33a24` |
| R5 Executor/checkpoint 接线 | `ff1ec8e` |
| R6 回答、Memory 与 Safety 边界 | `70be00d` |
| R7 系统验收与本报告 | 本次提交 |

阶段三至此冻结。阶段四 Model Router 必须先把本地/主模型职责、fallback、安全升级、指标口径和
router on/off 基线写入 DEV_SPEC，再开始实现。
