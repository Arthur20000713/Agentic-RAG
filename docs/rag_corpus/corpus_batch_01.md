# Corpus Batch 01

本批次用于 V4.1 真实畜牧知识库质量闭环的第一批候选资料。所有内容均为人工摘要、关键事实方向和引用锚点，不复制来源全文。

## 入库原则

- 优先入库低版权风险来源的人工摘要和链接。
- 对 Extension、政府报告和国际组织资料，先保留来源元数据、主题、适用场景和关键事实方向。
- 对药物、处方、停药期、诊断结论等高风险内容，只作为 redteam/reference 边界，不生成确定性治疗建议。
- 本批次 collection 目标为 `livestock_v4_1`。

## 来源摘要

| source_id | 入库策略 | 适合问题 | 人工摘要 |
|---|---|---|---|
| `umn_preweaning_calf_health` | summary only | 犊牛腹泻、呼吸道观察、断奶前健康巡检 | 用于回答断奶前犊牛健康观察、腹泻和呼吸道异常识别的基础问题；强调观察、记录和及时转兽医。 |
| `uga_raising_dairy_heifers` | summary only | 初乳、饲喂、断奶、后备牛记录 | 用于后备母牛出生到断奶阶段管理问题；覆盖饲喂、清洁、记录和阶段性管理。 |
| `usda_aphis_scours_dairy_calves` | summary only | 腹泻发生、统计事实、管理风险 | 用于评测腹泻相关统计和管理因素；不把历史调查数据写成当前全球通用结论。 |
| `usda_aphis_preweaned_calf_management` | summary only | 断奶前饲养、健康记录、管理做法 | 用于构造真实 RAG answerable 题和统计事实题；标注美国 NAHMS 调查语境。 |
| `penn_state_biosecurity_cattle_farms` | summary only | 生物安全、隔离、访客和车辆管理 | 用于牛场生物安全常识和 redteam 边界；强调隔离、清洁、访客控制和兽医协作。 |
| `penn_state_monitoring_dairy_heifer_growth` | summary only | 体重、体高、胸围、生长记录 | 用于体尺报告和后备牛生长监测问题；不复制图表，只记录指标类型和解释边界。 |
| `wisconsin_water_for_dairy_calves` | summary only | 犊牛饮水、采食、饲喂管理 | 用于回答饮水供应与犊牛采食、健康管理的关系。 |
| `wisconsin_air_quality_for_calves` | summary only | 通风、空气质量、呼吸道风险 | 用于回答圈舍空气质量、湿度、氨气和呼吸健康相关问题。 |
| `wisconsin_cold_stress_calves` | summary only | 冷应激、环境、能量需求 | 用于寒冷环境下犊牛护理和饲喂管理建议；需标注地域和气候差异。 |
| `fda_judicious_antimicrobial_use_209` | reference only | 抗菌药审慎使用、兽医监督、食品动物安全 | 用于安全拒答和 redteam，不输出剂量、处方或停药期；法域限定为美国监管语境。 |
| `fao_amr_livestock_resources` | summary only | AMR、畜牧抗菌药治理、生物安全 | 用于高层原则和安全边界；具体国家法规需另找本地来源。 |
| `tianjin_replacement_heifer_management` | summary only | 中文后备牛饲养、断奶、阶段管理 | 用于中文知识库和评测题；入库前复核政府页面版权和转载声明。 |

## 引用锚点

- 每个入库摘要必须保留 `source_id` 和 `source_uri`。
- 真实 RAG 回答中的 citation 不能只写机构名，必须能追溯到具体来源链接。
- 如果后续准备本地摘要文件，建议路径为 `C:\tmp\livestock_corpus\batch_01\<source_id>.md`，并由用户确认后再执行 RAG-SERVER 入库。
