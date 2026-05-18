# RAG Corpus Ingestion Plan

本文档记录 V4.1 第一批真实畜牧资料的入库计划。它不直接执行 RAG-SERVER 入库，也不要求修改 RAG-SERVER 代码或配置。

## 目标 Collection

- Agentic RAG 目标 collection：`livestock_v4_1`
- RAG-SERVER 执行前必须由用户确认 collection、资料文件和环境变量。
- 如果真实 RAG-SERVER 当前 collection 与本计划不一致，preflight 应报告 warning，不允许静默切回 fake。

## 入库分层

| 分层 | source_id | 入库内容 | 说明 |
|---|---|---|---|
| 人工摘要入库 | `umn_preweaning_calf_health` | 摘要、关键事实、链接 | 断奶前犊牛健康观察，避免复制网页全文。 |
| 人工摘要入库 | `uga_raising_dairy_heifers` | 摘要、关键事实、链接 | 出生到断奶阶段管理，避免复制 Extension 原文。 |
| 人工摘要入库 | `usda_aphis_scours_dairy_calves` | 摘要、统计事实、链接 | 只记录调查语境和少量事实锚点，不复制大段 PDF。 |
| 人工摘要入库 | `usda_aphis_preweaned_calf_management` | 摘要、统计事实、链接 | 只记录调查语境和管理主题，不复制大段 PDF。 |
| 人工摘要入库 | `penn_state_biosecurity_cattle_farms` | 摘要、关键事实、链接 | 生物安全、隔离和访客管理。 |
| 人工摘要入库 | `penn_state_monitoring_dairy_heifer_growth` | 摘要、指标说明、链接 | 不复制图表，保留体尺指标解释边界。 |
| 人工摘要入库 | `wisconsin_water_for_dairy_calves` | 摘要、关键事实、链接 | 犊牛饮水与采食管理。 |
| 人工摘要入库 | `wisconsin_air_quality_for_calves` | 摘要、关键事实、链接 | 空气质量、通风和呼吸健康。 |
| 人工摘要入库 | `wisconsin_cold_stress_calves` | 摘要、关键事实、链接 | 冷应激和环境管理。 |
| reference/redteam | `fda_judicious_antimicrobial_use_209` | 安全边界摘要、链接 | 用于审慎用药和高风险拒答，不生成处方、剂量或停药期。 |
| 人工摘要入库 | `fao_amr_livestock_resources` | 摘要、原则、链接 | AMR 和畜牧抗菌药治理原则。 |
| 人工摘要入库 | `tianjin_replacement_heifer_management` | 摘要、关键事实、链接 | 中文后备牛管理资料，入库前复核页面版权和转载声明。 |

当前批次不规划任何 `approved_full_text` 入库。后续如需全文入库，必须先确认来源许可、文件路径和用户授权。

## 本地文件占位规则

用户确认后，建议把人工摘要文件放在：

```text
C:\tmp\livestock_corpus\batch_01\<source_id>.md
```

每个本地摘要文件建议包含：

- `source_id`
- `title`
- `source_uri`
- `language`
- `organization`
- `ingestion_status`
- 人工摘要
- 关键事实
- 不确定性和安全边界

## RAG-SERVER 操作边界

以下命令只作为用户确认后的执行参考，不由检查脚本自动运行：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.venv\Scripts\python.exe scripts\check_rag_corpus.py --manifest docs\rag_corpus\source_manifest.yaml --corpus-root C:\tmp\livestock_corpus\batch_01 --dry-run
```

如果 dry-run 通过，再由用户确认是否进入 RAG-SERVER 入库流程。Agentic RAG 只读检查不得打印 API key，不得修改 RAG-SERVER 源码或配置。

## 当前阻塞项

- 本仓库尚未保存本地摘要文件。
- 真实 RAG-SERVER 是否已有 `livestock_v4_1` collection 需要后续 preflight 确认。
- reference/redteam 来源不能直接生成治疗处方或监管结论。
