# V4.2 知识库批次指南

V4.2 把真实畜牧知识库扩展整理成本地可审计流程。本应用侧只生成计划、校验批次、运行真实评测和质量门禁，不修改 RAG-SERVER 代码或配置。

## 资产

- `docs/rag_corpus/source_manifest.yaml`：当前启用的资料源清单。
- `docs/rag_corpus/manifests/livestock_v4_2.yaml`：`livestock_v4_2` collection 的版本化 manifest。
- `docs/rag_corpus/batches/batch_002.yaml`：第二批语料计划，记录 source_id、本地摘要路径、目标 collection 和质量门禁阈值。
- `docs/rag_corpus/reports/batch_002_quality.md`：批次质量报告模板和趋势记录区。
- `tests/fixtures/real_golden_v4_2/all.json`：V4.2 真实评测集。

## 流程

1. 人工确认 manifest 中的资料源元数据。
2. 按 batch 文件列出的路径准备本地人工摘要文件。
3. 运行批次校验：
   ```powershell
   .venv\Scripts\python.exe scripts\check_v4_2.py --stage full
   ```
4. 生成 RAG-SERVER 入库计划：
   ```powershell
   .venv\Scripts\python.exe scripts\check_rag_corpus.py --batch docs\rag_corpus\batches\batch_002.yaml --dry-run
   ```
5. 用户确认资料文件和 RAG-SERVER 环境后，手动执行生成的 RAG-SERVER 入库命令。
6. 运行真实批次回归和质量门禁：
   ```powershell
   $env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
   .\scripts\check_real_batch.ps1 -Batch docs\rag_corpus\batches\batch_002.yaml -OutputDir reports\real_v4_2_batch
   ```

## 质量门禁

`batch_002.yaml` 定义最低阈值：

- 总通过率：`0.90`
- no-answer 准确率：`0.95`
- source URI 覆盖率：`0.95`
- safety 通过率：`1.00`

skipped real eval report 只能作为诊断材料，不能算作门禁通过。如果 RAG-SERVER 中缺少 `livestock_v4_2`，preflight 应报告 `RAG_COLLECTION_NOT_FOUND`。

## 边界

- 不提交版权不明的全文资料。
- 不打印或提交 API key。
- 不用 fake mode 代替真实质量门禁。
- 未经用户明确授权，不修改 RAG-SERVER 仓库代码或配置。
