# V4.1 阶段完成报告

## 1. 阶段范围

V4.1 已按 `DEV_SPEC_v4_1.md` 完成 A 到 I 阶段开发。该阶段没有修改 sibling `RAG-SERVER` 源码，重点放在 Agentic RAG 应用层的真实资料源治理、真实评测集、低置信拒答、V3 主路径开关、trace/debug 可观测性、真实 RAG preflight 和发布文档。

## 2. 已完成能力

- V4.1-A：固化当前基线，新增 V4.1 检查入口。
- V4.1-B：新增资料源 manifest 解析和校验模型，建立第一批真实资料源清单。
- V4.1-C：编写第一批真实语料入库计划，并新增入库前检查脚本。
- V4.1-D：增强真实 RAG preflight，输出 manifest collection、目标 collection、资料源数量和 mismatch warning。
- V4.1-E：扩展真实评测集结构，新增 answerable、no-answer、safety 三组真实 RAG 评测样本。
- V4.1-F：新增真实 RAG 低置信策略配置，并在 mapper 中硬化低置信拒答和失败分类。
- V4.1-G：明确 V3 API 主路径接入决策，按 `v3.enabled` 配置切换 `/api/chat` 主路径。
- V4.1-H：贯通请求级 trace 查询，补强真实评测 source quality 摘要。
- V4.1-I：更新运行和评测文档，完成全量回归和本阶段报告。

## 3. 回归验证

以下命令均使用项目根目录 `.venv` 执行。

| 验证项 | 命令 | 结果 |
|---|---|---|
| 默认非真实 RAG 回归 | `.venv\Scripts\python.exe -m pytest -m "not rag_server" -q` | `298 passed, 3 deselected` |
| V2 离线、前端契约和文档检查 | `.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs` | `V2 checks passed` |
| V3 full 检查 | `.venv\Scripts\python.exe scripts\check_v3.py --stage full` | `V3 checks passed for stage full` |
| V4.1 full 检查 | `.venv\Scripts\python.exe scripts\check_v4_1.py --stage full` | `V4.1 checks passed for stage full` |
| 真实 RAG marker 测试 | `$env:RAG_SERVER_PATH='C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER'; .venv\Scripts\python.exe -m pytest -m rag_server -q` | `3 passed, 298 deselected` |
| 真实 RAG optional eval | `$env:RAG_SERVER_PATH='C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER'; .venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir .tmp_tests\real_v4_1` | 已生成完整报告；退出码为 `1`，原因是存在 5 个评测失败用例 |

## 4. 真实 RAG 评测结论

本次真实 RAG optional eval 没有静默 fallback 到 fake。输出目录为 `.tmp_tests\real_v4_1`，包含：

- `real_rag_preflight.json`
- `eval_result.json`
- `eval_result.csv`
- `eval_summary.md`
- `failure_analysis.md`

preflight 结果：

- `status`: `passed`
- target collection: `default`
- manifest collection: `livestock_v4_1`
- manifest source count: `12`
- tools: `query_knowledge_hub`, `list_collections`, `get_document_summary`
- collections: `default`
- warnings: `RAG_COLLECTION_MISMATCH`, `SOURCE_MANIFEST_COLLECTION_MISMATCH`

评测结果：

- total cases: `60`
- passed cases: `55`
- failed cases: `5`
- pass rate: `91.67%`
- `rag_citation_coverage`: `100.00%`
- `source_uri_coverage`: `100.00%`
- `safety_pass_rate`: `100.00%`
- `no_answer_accuracy`: `0.00%`
- failure category: `NO_ANSWER_FALSE_POSITIVE: 5`

因此，V4.1 已满足“真实 RAG 可完成并输出失败归因”的工程验收要求，但真实知识库质量仍未达到产品级 no-answer 验收目标。

## 5. 剩余风险

- Agentic RAG 当前真实评测目标 collection 仍为 `default`，而 V4.1 manifest 期望 collection 为 `livestock_v4_1`；RAG-SERVER 配置中默认 collection 也不一致，preflight 已明确报告 mismatch。
- 当前真实 RAG 可连通并可评测，但知识库仍不足以支撑 no-answer 质量目标，5 个 no-answer case 被错误回答。
- V4.1 仅准备了治理后的 source manifest 和入库计划，没有在本仓库内提交版权受限资料全文，也没有修改 RAG-SERVER 代码。
- 后续若要达到产品级真实 RAG 验收，需要先确认可入库资料、执行真实入库，并把应用侧 collection 切换到目标知识库后重新评测。

## 6. 交付状态

V4.1 开发阶段已完成并具备可回归、可诊断、可继续推进真实知识库建设的工程基线。下一阶段建议优先处理 `livestock_v4_1` 真实语料入库和 no-answer 质量闭环，而不是继续扩大 agent 功能面。
