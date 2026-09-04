# Corpus Batches

本目录保存真实知识库入库批次计划。每个 batch 文件描述目标 collection、对应 manifest、计划入库来源、本地人工摘要文件路径和质量门禁。

## 状态约定

- `planned`：已规划，可能尚未准备本地摘要文件，不能当作已入库。
- `ready`：本地文件已准备，可执行 dry-run 和用户确认后的真实入库。
- `ingested`：已执行真实入库，并应有对应质量报告。
- `not_ingested`：暂不入库，仅保留计划记录。

## 执行边界

- batch 可以引用仓库内可分发的原创摘要，但不提交版权受限全文或原始网页/PDF 快照。
- `local_file` 使用仓库相对路径时，dry-run 会输出绝对路径，确保命令可在 sibling RAG-SERVER 工作目录执行。
- `scripts/check_v4_2.py --stage batch` 会校验 batch schema 和 manifest 对齐。
- `scripts/check_rag_corpus.py --batch <path> --dry-run` 用于生成 RAG-SERVER 入库命令，不默认执行。
