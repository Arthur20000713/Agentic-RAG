# RAG Corpus Governance

本目录用于维护真实畜牧知识库的资料治理资产。这里保存来源元数据、批次计划、原创摘要、来源校验记录和质量报告，不保存版权受限全文、API key 或 RAG-SERVER 私有配置。

## 目录

- `source_manifest.yaml`：当前开发阶段默认使用的资料源清单。
- `manifests/`：按 collection 版本保存的资料源清单快照。
- `batches/`：每一批计划入库资料的 batch 文件。
- `content/`：可分发的原创摘要及其 provenance；文件扩展名使用 RAG-SERVER 实际支持的 `.txt`。
- `reports/`：每一批入库后的 preflight、eval 和 quality gate 摘要。
- `ingestion_plan.md`：真实入库前的人工执行计划和约束。

## 使用规则

- 每个来源必须有 `source_id`、`source_uri`、语言、机构、用途和许可备注。
- `usage` 用于区分 `knowledge_base`、`eval`、`redteam` 和 `reference`。
- `ingestion_status` 为 `approved_summary_only` 或 `approved_full_text` 时，才可进入入库 dry-run。
- `reference_only` 和 `eval_only` 来源只能用于引用、安全边界或评测设计，不应直接入库全文。
- 机器辅助摘要必须标明抓取日期、原始响应 SHA256 和待人工签字状态，不能沿用不可验证的 `reviewed_by: human`。
- 执行真实入库前必须先运行 V4.2 batch 检查和 dry-run 命令生成。
