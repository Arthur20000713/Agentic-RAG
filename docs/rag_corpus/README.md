# RAG Corpus Governance

本目录用于维护真实畜牧知识库的资料治理资产。这里保存的是来源元数据、批次计划、质量报告和人工摘要入口，不保存版权受限全文、API key 或 RAG-SERVER 私有配置。

## 目录

- `source_manifest.yaml`：当前开发阶段默认使用的资料源清单。
- `manifests/`：按 collection 版本保存的资料源清单快照。
- `batches/`：每一批计划入库资料的 batch 文件。
- `reports/`：每一批入库后的 preflight、eval 和 quality gate 摘要。
- `ingestion_plan.md`：真实入库前的人工执行计划和约束。

## 使用规则

- 每个来源必须有 `source_id`、`source_uri`、语言、机构、用途和许可备注。
- `usage` 用于区分 `knowledge_base`、`eval`、`redteam` 和 `reference`。
- `ingestion_status` 为 `approved_summary_only` 或 `approved_full_text` 时，才可进入入库 dry-run。
- `reference_only` 和 `eval_only` 来源只能用于引用、安全边界或评测设计，不应直接入库全文。
- 执行真实入库前必须先运行 V4.2 batch 检查和 dry-run 命令生成。
