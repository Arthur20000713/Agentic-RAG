# V4.2 完成报告

日期：2026-05-18

## 阶段结论

V4.2 的 Agentic RAG 侧工程闭环已完成：source manifest、corpus batch、dry-run 入库计划、V4.2 真实评测集、real eval batch 参数、质量门禁、报告 diff、前端 RAG 调试状态和文档入口均已落地。

真实 RAG 链路已完成端到端验收：RAG-SERVER 可通过 MCP stdio 启动，`livestock_v4_2` collection 可被 preflight 发现，V4.2 batch real eval 可跑完并通过质量门禁。Agentic RAG 侧新增了真实 RAG 回答策略：低置信检索结果保留在观测数据中，但不进入可用上下文；明显越界、无入库事实、受限全文复制、处方/剂量/停药期/确定性诊断等请求在真实检索后稳定拒答，不静默回退 fake。

## 本次验证

| 检查 | 结果 |
|---|---|
| `.venv\Scripts\python.exe -m pytest -m "not rag_server" -q` | 通过：398 passed, 3 deselected |
| `.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs` | 通过 |
| `.venv\Scripts\python.exe scripts\check_v3.py --stage full` | 通过 |
| `.venv\Scripts\python.exe scripts\check_v4_1.py --stage full` | 通过 |
| `.venv\Scripts\python.exe scripts\check_v4_2.py --stage full` | 通过 |
| `.venv\Scripts\python.exe -m pytest -m rag_server -q` | 通过：3 passed, 398 deselected |
| `scripts\run_eval.py --mode real --optional --batch ... --output-dir .tmp_tests\real_rag_fill_regression` | 通过：80/80，pass rate 100% |
| `scripts\check_v4_2.py --stage gate --report .tmp_tests\real_rag_fill_regression\eval_result.json --batch ...` | 通过：Quality gate passed |

## 真实 RAG 诊断摘要

- 目标 collection：`livestock_v4_2`
- batch：`batch_002`
- manifest collection：`livestock_v4_2`
- manifest source count：18
- RAG-SERVER 当前 collections：`default`、`livestock_v4_2`
- RAG-SERVER MCP tools：`query_knowledge_hub`、`list_collections`、`get_document_summary`
- 诊断 error code：无
- 诊断 warning：`RAG_COLLECTION_MISMATCH`
- RAG-SERVER config 中 vector store 默认 collection：`knowledge_hub`
- Agentic RAG 本次 batch collection：`livestock_v4_2`
- API key 仅检查是否存在，未打印、未提交明文。

## 真实评测摘要

| 指标 | 结果 |
|---|---:|
| total cases | 80 |
| passed cases | 80 |
| pass rate | 100.00% |
| intent accuracy | 100.00% |
| rag call accuracy | 100.00% |
| citation coverage | 100.00% |
| no-answer accuracy | 100.00% |
| safety pass rate | 100.00% |
| source_uri coverage | 100.00% |
| RAG error count | 0 |

## 已完成能力

- 可校验的 V4.2 source manifest：`docs/rag_corpus/manifests/livestock_v4_2.yaml`
- 可审计的 batch 文件：`docs/rag_corpus/batches/batch_002.yaml`
- 只读入库 dry-run：`scripts/check_rag_corpus.py --batch ... --dry-run`
- V4.2 真实评测集：`tests/fixtures/real_golden_v4_2/all.json`
- 质量门禁：`scripts/check_v4_2.py --stage gate --report ... --batch ...`
- 真实批次回归脚本：`scripts/check_real_batch.ps1`
- 报告对比工具：`scripts/diff_eval_reports.py`
- 前端 Debug RAG 状态展示：`rag_status`、collection、batch、quality gate 状态。

## 后续复验命令

真实 batch quality gate 当前已通过。后续若更新语料、重建 collection 或调整 RAG-SERVER 配置，需要重新运行：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.\scripts\check_real_batch.ps1 -Batch docs\rag_corpus\batches\batch_002.yaml -OutputDir reports\real_v4_2_batch
```

若失败，应优先查看输出目录中的 `real_rag_preflight.json`、`eval_result.json` 和 `failure_analysis.md`，不要切换到 fake mode 替代真实门禁。
