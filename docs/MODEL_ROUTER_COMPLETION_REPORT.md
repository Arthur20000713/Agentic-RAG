# Model Router MR6 系统验收报告

## 1. 验收结论

MR0–MR5 的实现、离线测试和 scripted A/B 均已完成。MR6 已执行真实主模型、本地 Qwen、真实 RAG、
E2E 和全量非 Docker 回归，但真实质量门禁未通过，因此本阶段不能标记完成，也不能启用
`livestock_triage` takeover 或对外声明 latency、tokens、cost 收益。

当前生产配置的 takeover allowlist 不包含 `livestock_triage`。不合格的本地模型输出继续 fail closed，
不会进入 Planner、RAG evidence、Memory、citation 或用户可见答案。

## 2. 本次真实环境

| 项目 | 实际值 |
|---|---|
| 主模型 | OpenAI-compatible `gpt-5.6-luna` |
| 主模型端点 | `https://api.a6api.com` |
| 本地模型 | Transformers `Qwen/Qwen2.5-0.5B-Instruct` |
| 本地运行设备 | CPU；当前 PyTorch 无 CUDA |
| RAG 模式 | real |
| collection | `livestock_v4_2` |
| A/B 场景 | router_off / router_shadow / router_on |
| warm-up | 每场景 1 次完整图 representative case |
| measured repeats | 每 case、每场景 3 次 |
| 执行顺序 | rotating scenario order |
| 真实 A/B 时段 | 2026-09-03 15:15:28–16:35:39，约 80 分钟 |

API key 仅保存在 Git 忽略的项目 `.env` 中。报告、trace、测试输出和 commit 均不包含密钥。

## 3. 主模型迁移与连通性

主模型已从 DeepSeek 切换到 A6 OpenAI-compatible API。该端点的模型列表包含
`gpt-5.6-luna`，认证请求成功。

供应商对 `response_format` 或 `temperature` 参数不会快速返回兼容性错误，而会持续等待直至客户端超时；
项目请求已按供应商示例移除这两个可选参数，继续使用 system prompt 和严格 JSON parser 约束结构化输出。

通过项目 `PrimaryLLMClient` 的真实烟雾测试结果：

- status：success；
- provider/model：`openai / gpt-5.6-luna`；
- 成功 attempt latency：2494 ms；
- usage：36 input、14 output、50 total tokens；
- fallback：无。

该次调用首个 attempt 曾触发 30 秒超时，现有一次重试随后成功。真实 A/B 也记录到
`PRIMARY_LLM_TRANSPORT_ERROR`，因此尾延迟和 token 完整性未达到声明标准。

## 4. 真实 Router A/B 结果

工件目录：`.tmp_tests/router_ab_real_mr6_a6/`。其中包含 `eval_result.json`、
`eval_result.csv`、`eval_summary.md`、`agent_runtime_report.json`、
`agent_runtime_report.md` 和 `real_rag_preflight.json`。

| 场景 | task success | E2E P50/P95 ms | 模型 P50/P95 ms | 已知 tokens | fallback | 本地接管 accepted | Safety |
|---|---:|---:|---:|---:|---:|---:|---:|
| router_off | 33.33% | 47547.969 / 185295.622 | 32063.5 / 170468.2 | 24108 | 33.33% | 0 | 100% |
| router_shadow | 33.33% | 65433.420 / 236348.429 | 54252.5 / 228493.6 | 21964 | 77.78% | 0 | 100% |
| router_on | 33.33% | 55834.491 / 211413.233 | 40359.0 / 204713.75 | 38263 | 77.78% | 0 | 100% |

共 54 个 measured case，18 passed、36 failed。36 个失败全部归类为 `MISSING_CITATION`。
真实 RAG preflight 通过，三种场景分别执行 37、36、32 次实际 RAG 调用，但需要 evidence 的 case
没有得到可引用结果。S3/S4 的本地调用数均为 0，S4 实际 RAG 调用数均为 0。

`claim_eligibility.task_success/latency/tokens/cost` 全部为 false，quality gate 为
`not_eligible`。主模型定价未配置，cost 保持 `null`；本报告不把已知 token 的零价格快照解释为零成本。

## 5. 本地 Qwen 诊断

真实 A/B 中：

- router_on 发起 12 次本地 takeover，accepted 为 0；
- router_shadow/local success 为 0；
- intent accuracy 为 0，slot accuracy 为 0.5，risk accuracy 为 0；
- 本地失败稳定回退主模型，高风险请求从未进入本地模型。

审计发现业务层和 Transformers backend 原先各构造一次 triage prompt，导致提示词嵌套。该问题已修复，
现在业务层只传原始 query，由 backend 统一构造 schema prompt。当前提交上的真实单例仍以
`LOCAL_MODEL_SCHEMA_ERROR` 安全回退。隔离实验将输出上限提高到 192/256 后，0.5B 模型虽然能闭合 JSON，
仍产生非法 intent、对象型 slots、伪造 source span、风险降级和未出现的事实。

这些输出不得通过强制覆盖 intent/risk 或自动信任 slots 来“修复”，否则会绕过 grounding guard 并伪造
模型质量。要通过门禁，需要更强的本地 instruct 模型、JSON-schema constrained decoding 或经合格数据验证的
专项 LoRA；本机当前只有 0.5B 缓存，Ollama 不可用。

## 6. 回归证据

| 范围 | 结果 |
|---|---:|
| 主模型迁移目标测试 | 63 passed |
| 完整 unit | 470 passed |
| eval runner integration | 25 passed |
| triage prompt ownership 目标回归 | 61 passed |
| E2E | 29 passed |
| 全量非 Docker、非真实 RAG | 790 passed，3 deselected |

直接执行 `pytest -m "not rag_server"` 时，790 个测试断言通过，但两份未标记的 Docker/MySQL migration
文件产生 3 个 fixture error，原因是 Docker `run` 返回 127。显式排除这两份 Docker 专用文件后，
非 Docker 全量 790 项通过。该环境问题不计为本次代码回归通过，也未伪装成 skip。

## 7. 未完成条件

MR6 保持“验收未通过”，直至同时满足：

1. 为 `livestock_v4_2` 提供能命中 golden queries 的真实语料和 citation；
2. 本地 triage 在固定 golden set 上达到 intent/slot/risk 门禁，并至少有一次安全 accepted takeover；
3. 供应商提供可审计的 input/output token 单价，或明确接受 cost claim 不参与 gate 的新产品决策；
4. 真实 A/B 的 task success、tokens 和 fallback 证据完整，quality gate 通过；
5. 再次运行 E2E、全量非 Docker 回归与 staged diff 审核。

## 8. 相关提交

| 内容 | Commit |
|---|---|
| MR0 规范 | `c0dae07` |
| MR1 路由与 usage 契约 | `9690b28` |
| MR2 本地 triage | `f43c580` |
| MR3 Graph 与 checkpoint | `ae04d02` |
| MR4 用量与成本遥测 | `952f21f` |
| MR5 A/B 与质量门禁 | `c2076ce`、`75e844e` |
| 主模型迁移至 A6 | `ce8fb0e` |
| 消除 triage 双重 prompt | `fdb430c` |
