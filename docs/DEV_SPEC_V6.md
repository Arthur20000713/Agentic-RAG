# V6 产品化收口开发规范

## 目标

V6 的目标是把当前“本机真实 RAG 可演示”推进到“本机真实应用可稳定试用”。本阶段不重写 RAG-SERVER，不扩大 LoRA 训练范围，优先补齐启动、配置、诊断、真实 RAG 默认路径、中文问答质量、前端诊断和发布检查。

## 当前基线

- Agentic RAG 默认配置已启用真实 RAG。
- 默认 collection 为 `livestock_v4_2`。
- V4.2 batch `batch_002` 已通过真实 RAG 质量门禁，80/80 passed。
- 本地 Transformers 后端已实现并通过真实权重 smoke，但默认未启用。
- LoRA 仍处于数据治理、训练编排和受控推理框架阶段，未默认启用真实 adapter。

## 原则

- 默认应用路径必须使用真实 RAG，不允许静默退回 fake。
- 默认检查可以不启动真实外部依赖，但必须能发现配置退化。
- 运行脚本必须给出明确错误码和下一步命令。
- 业务回答质量优化必须保留 citation/source_uri。
- 高风险兽医结论、处方、剂量、停药期和确定性诊断仍必须被安全策略约束。
- 每个实质阶段完成后必须 commit and push。

## 阶段计划

| 阶段 | 目标 | 主要产物 | 验收 |
|---|---|---|---|
| V6.0-A0 | 建立 V6 开发规范 | `docs/DEV_SPEC_V6.md` | 文档包含阶段、验收、进度表 |
| V6.0-A1 | 建立 V6 检查入口 | `scripts/check_v6.py`、`tests/integration/test_check_v6.py` | `check_v6.py --stage baseline` 通过 |
| V6.1-B | 一键启动和运行时诊断 | `scripts/start_app.ps1`、运行时 doctor | 能检测端口、RAG-SERVER 路径、Python、collection |
| V6.2-C | 应用健康和 readiness | `/api/health`、`/api/ready` | 健康接口区分应用存活、真实 RAG 可用、质量门禁状态 |
| V6.3-D | 真实 RAG 回答质量优化 | 回答合成层、中文问答回归 | 返回自然语言答案，不只展示检索结果 |
| V6.4-E | V3/V5 主路径灰度启用 | 配置、路由、debug 可观测 | 低风险结构化任务可控接管，高风险仍走安全路径 |
| V6.5-F | 本地模型 GPU 验收 | Transformers GPU smoke、运行文档 | 3060 Laptop 6GB 上完成 query normalization smoke |
| V6.6-G | 产品化发布检查 | release checklist、CI 候选脚本 | 一条命令输出可试用/不可试用结论 |

## V6.0 验收命令

```powershell
.venv\Scripts\python.exe scripts\check_v6.py --stage baseline
.venv\Scripts\python.exe -m pytest tests\integration\test_check_v6.py -q
.venv\Scripts\python.exe -m pytest -m "not rag_server" -q
```

## 进度跟踪

| 阶段 | 状态 | 说明 |
|---|---|---|
| V6.0-A0 | IN_PROGRESS | 编写 V6 开发规范 |
| V6.0-A1 | IN_PROGRESS | 新增 V6 baseline 检查入口 |
| V6.1-B | TODO | 一键启动和运行时诊断 |
| V6.2-C | TODO | 健康/readiness API |
| V6.3-D | TODO | 真实 RAG 回答质量优化 |
| V6.4-E | TODO | V3/V5 主路径灰度启用 |
| V6.5-F | TODO | 本地模型 GPU 验收 |
| V6.6-G | TODO | 产品化发布检查 |

