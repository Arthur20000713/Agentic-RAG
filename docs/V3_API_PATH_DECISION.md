# V3 API Path Decision

本文档记录 V4.1-G 对 `/api/chat` 主路径的接入决策。

## 决策

- 默认生产/本地演示路径仍为 V2 workflow。
- 只有当 `config/settings.yaml` 或测试配置中显式设置 `v3.enabled=true` 时，`/api/chat` 才允许走 V3 agent graph。
- `v3.enabled=false` 时，现有 `/api/chat` 响应 contract 不应破坏。

## 边界

- V3 graph 是可选主路径，不代表 local model 或 LoRA 已成为真实生产推理能力。
- `local_model.provider="mock"` 仍是结构化 mock。
- LoRA 当前仍是数据治理和导出 dry-run，不包含真实训练或推理启用。
- 真实 RAG 仍由 `rag_server.query_mode` 和 `RAG_SERVER_PATH` 显式控制，不允许为了让 V3 跑通而静默切回 fake。

## 接入规则

| 配置 | `/api/chat` 行为 |
|---|---|
| `v3.enabled=false` | 使用 V2 workflow：`run_general_qa`、`run_disease_consultation`、`run_measurement_analysis`。 |
| `v3.enabled=true` 且 intent 为 `general_qa` 或 `feeding_management` | 使用 `run_general_qa_graph`。 |
| `v3.enabled=true` 且 intent 为 `disease_consultation` 或高风险拒答 | 使用 `run_disease_graph`。 |
| measurement 请求 | 继续使用现有 measurement workflow，避免扩大本阶段变更面。 |

## 验收重点

- V3 关闭时，现有 API contract 和前端 demo 不变。
- V3 开启时，响应中保留可调试的 `v3_debug`、agent path、safety 和 verifier 信息。
- 测试必须覆盖 V3 disabled regression，避免主路径切换引入回归。
