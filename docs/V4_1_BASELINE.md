# V4.1 Baseline

本文档固化 V4.1 开发起点，避免后续阶段重复实现已经完成的 V3/V4.0 能力。

## 当前阶段

- 当前阶段位于 V4.0-E 之后。
- V4.0-E 已完成真实 RAG-SERVER MCP stdio 接入、preflight、timeout retry、source_uri/citation 映射和真实 eval 报告。
- V4.1 的重点不是重新开发 RAG 链路，而是建设真实畜牧知识源、真实评测集、no-answer 闭环和产品化验收检查。

## 已完成能力边界

- V1/V2 已完成 FastAPI、SQLite、静态前端、RAG fake/smoke/real 模式、trace、eval 和基础任务接口。
- V3 已完成 feature flags、SafetyPrecheck、ModelRouter shadow、结构化任务接管、Verifier 增强、LoRA 数据治理 dry-run、Memory MVP 和 V3 eval/debug summary。
- V4.0 已完成真实 RAG-SERVER adapter 稳定化，真实模式不可静默 fallback 到 fake。

## 默认运行边界

- `v3.enabled` 默认关闭，`/api/chat` 默认仍走 V2 workflow。
- `local_model.provider="mock"` 是结构化 mock，不代表真实本地大模型推理能力。
- LoRA 当前只覆盖数据治理、导出和 dry-run，不包含真实训练或推理启用。
- 真实 RAG 必须显式配置 `RAG_SERVER_PATH`，未配置时 optional real eval 只能生成 skipped report。

## 当前真实 RAG 质量问题

- 真实 RAG 链路已经可以跑通，当前主要问题不是 MCP 链路不可用。
- 当前 RAG-SERVER 知识库样本仍偏弱，真实 eval 失败集中在 no-answer 和弱相关召回场景。
- 下一阶段需要用真实畜牧资料建设可治理的 source manifest、corpus plan 和分组 golden set。
- 评测重点应区分 answerable、no-answer 和 safety refusal，避免用 fake regression 证明真实 RAG 质量。

## V4.1 验收入口

V4.1 会新增统一检查脚本：

```powershell
.venv\Scripts\python.exe scripts\check_v4_1.py --stage baseline
.venv\Scripts\python.exe scripts\check_v4_1.py --stage corpus
.venv\Scripts\python.exe scripts\check_v4_1.py --stage full
```

这些检查脚本默认只读，不启动真实 RAG，不写入 reports。
