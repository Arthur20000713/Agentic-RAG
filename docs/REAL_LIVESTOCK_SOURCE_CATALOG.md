# 真实畜牧资料来源目录

> 用途：为后续真实 RAG 知识库建设、golden set 评测题设计、no-answer 评测和安全红队评测提供候选资料来源。
>
> 采集原则：优先官方机构、大学 Extension、国际组织、政府农技资料、开放获取论文和公开标准目录；不批量复制受版权保护全文；入库前逐条复核 robots、版权和许可声明。

## 使用边界

- 可以优先入库：政府/国际组织公开指南、大学 Extension 页面、明确开放许可资料，以及资料的自写摘要、元数据、链接和少量必要事实。
- 适合做评测题源：评分表、管理规范、统计报告、政策文件、标准目录和兽医安全边界资料。
- 不建议全文入库：商业兽医手册、行业协会 PDF、标准全文、CNKI/万方论文全文、转载型中文农技门户内容。
- 安全红队必须覆盖：具体用药剂量、确定性诊断、处方/停药期、病牛隔离、生物安全、兽医转诊提示和版权全文复述请求。

## 高质量来源候选

| # | 标题 | URL | 语言 | 来源类型 | 机构 | 主题标签 | 许可/使用说明 | 建议用途 | 摘要 | 风险备注 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Pre-weaning calf health | https://extension.umn.edu/dairy-youngstock/pre-weaning-calf-health | EN | University Extension | University of Minnesota Extension | 犊牛健康观察, 腹泻, 呼吸道 | 教育网页，建议链接+摘要 | eval, knowledge_base | 断奶前犊牛健康观察、腹泻和肺炎识别管理 | 不复制全文，批量采集前查 robots |
| 2 | Calf Health Scorer | https://www.vetmed.wisc.edu/fapm/svm-dairy-apps/calf-health-scorer-chs/ | EN | University tool | University of Wisconsin | 健康评分, 呼吸道, 腹泻 | 工具/教育资源 | eval, redteam | 标准化评分鼻涕、眼分泌物、咳嗽、体温等 | 评分表可能有版权，避免原样复刻 |
| 3 | Dairy Calf Health Scoring Chart PDF | https://www.vetmed.wisc.edu/fapm/wp-content/uploads/2021/11/calf_health_scoring_chart.pdf | EN | University PDF | University of Wisconsin | 健康评分, 呼吸道, 腹泻 | PDF，适合做题源 | eval | 犊牛粪便、鼻、眼、耳、咳嗽、体温评分 | PDF 版权/使用条款需复核 |
| 4 | Diarrhea in neonatal ruminants | https://www.msdvetmanual.com/digestive-system/intestinal-diseases-in-ruminants/diarrhea-in-neonatal-ruminants | EN | Veterinary manual | MSD Vet Manual | 腹泻, 鉴别诊断, 用药边界 | 商业医学手册，摘要/链接为主 | redteam, reference | 新生反刍动物腹泻病因、临床表现和处理原则 | 不复制全文；不能替代兽医诊断 |
| 5 | Enzootic pneumonia in calves | https://www.msdvetmanual.com/respiratory-system/respiratory-diseases-of-cattle/enzootic-pneumonia-in-calves | EN | Veterinary manual | MSD Vet Manual | 呼吸道病, 诊断边界 | 商业手册，引用链接 | redteam, reference | 犊牛地方性肺炎病因、风险和临床表现 | 不替代兽医诊断 |
| 6 | Raising dairy heifers from birth to weaning | https://extension.uga.edu/publications/detail.html?number=B1500 | EN | University Extension | University of Georgia Extension | 饲喂, 初乳, 断奶, 记录 | Extension 资料，摘要入库 | knowledge_base, eval | 从出生到断奶的后备母牛管理 | 复核页面版权 |
| 7 | Scours in dairy calves | https://www.aphis.usda.gov/sites/default/files/dairy07_dr_scours.pdf | EN | Government report/PDF | USDA APHIS NAHMS | 腹泻, 流行病学 | 政府资料，仍需查使用条款 | eval, knowledge_base | 奶牛场犊牛腹泻发生和管理调查 | 年份较旧，注意时效 |
| 8 | Dairy heifer raiser, preweaned calf management | https://www.aphis.usda.gov/animal_health/nahms/dairy/downloads/dairy14/Dairy14_dr_PartI_1.pdf | EN | Government report/PDF | USDA APHIS NAHMS | 饲喂, 记录, 健康管理 | 政府 PDF，适合统计事实题 | eval, knowledge_base | 美国奶牛场犊牛饲养、初乳、断奶调查 | PDF 较大，不全文复制 |
| 9 | Calf Care & Quality Assurance Manual | https://www.calfcareqa.org/Media/CalfCare/Docs/ccqa-manual_digital.pdf | EN | Industry guideline | Calf Care & Quality Assurance | 福利, 记录, 用药, 运输 | 行业手册，链接/摘要为主 | knowledge_base, redteam | 犊牛护理、质量保证、记录和福利综合手册 | 版权风险中等 |
| 10 | National Dairy FARM Animal Care Reference Manual | https://nationaldairyfarm.com/dairy-farm-standards/animal-care/ | EN | Industry standard | National Dairy FARM | 动物福利, 用药记录, 生物安全 | 标准/手册，记录版本号 | eval, knowledge_base | 美国奶牛动物护理标准与审核要求 | 版本更新快 |
| 11 | National Dairy FARM Everyday Biosecurity | https://nationaldairyfarm.com/dairy-farm-standards/everyday-biosecurity/ | EN | Industry guidance | National Dairy FARM | 生物安全, 访客, 车辆, 隔离 | 教育资料，摘要入库 | knowledge_base, eval | 奶牛场日常生物安全计划 | 疫病背景更新快 |
| 12 | NFACC Code of Practice for Dairy Cattle | https://www.nfacc.ca/codes-of-practice/dairy-cattle | EN/FR | National code | NFACC Canada | 动物福利, 犊牛饲养, 断奶 | 行业准则，查版权 | eval, knowledge_base | 加拿大奶牛福利、住房、犊牛管理规范 | 不复制全文，引用章节 |
| 13 | WOAH Terrestrial Code | https://www.woah.org/en/what-we-do/standards/codes-and-manuals/terrestrial-code-online-access/ | EN/FR/ES | International standard | WOAH | 动物福利, 国际规范 | 官方标准，查在线条款 | eval, knowledge_base | 动物福利和奶牛生产系统相关原则 | 引用前核对最新版 |
| 14 | WOAH prudent antimicrobial use | https://www.woah.org/en/what-we-do/standards/codes-and-manuals/terrestrial-code-online-access/ | EN/FR/ES | International standard | WOAH | 用药安全, 抗菌药, AMR | 官方标准，适合安全边界 | redteam, eval | 兽用抗菌药审慎使用原则 | 需定位最新版具体章节 |
| 15 | FDA Guidance #209 | https://www.fda.gov/regulatory-information/search-fda-guidance-documents/cvm-gfi-209-judicious-use-medically-important-antimicrobial-drugs-food-producing-animals | EN | Government guidance | US FDA CVM | 用药安全, 抗菌药 | 美国政府指南，摘要引用 | redteam, eval | 食品动物重要抗菌药审慎使用原则 | 美国监管语境 |
| 16 | FDA extra-label drug use in animals | https://www.fda.gov/animal-veterinary/resources-you/animal-drug-compounding-and-extra-label-drug-use | EN | Government guidance | US FDA | 用药边界, 处方, 禁忌 | 政府网页 | redteam | 动物超标签用药监管框架 | 法域限定，不泛化到中国 |
| 17 | CFSPH biosecurity resources | https://www.cfsph.iastate.edu/biosecurity/ | EN | University/government resource | Iowa State CFSPH | 生物安全, 疫病防控 | 教育资源，链接/摘要 | knowledge_base, eval | 农场生物安全培训和清单 | 逐项核对许可 |
| 18 | Biosecurity for dairy and beef cattle farms | https://extension.psu.edu/biosecurity-for-dairy-and-beef-cattle-farms | EN | University Extension | Penn State Extension | 生物安全, 隔离, 访客 | Extension 页面，摘要入库 | knowledge_base | 牛场生物安全措施概览 | 不复制全文 |
| 19 | Monitoring dairy heifer growth | https://extension.psu.edu/monitoring-dairy-heifer-growth | EN | University Extension | Penn State Extension | 体尺, 体重, 生长监测 | Extension 页面 | eval, knowledge_base | 体重、体高、胸围等生长监测 | 数值表格复制需谨慎 |
| 20 | Dairy heifer growth charts | https://extension.psu.edu/dairy-heifer-growth-charts | EN | University Extension | Penn State Extension | 体重, 体尺, 目标生长 | Extension 图表 | eval | 后备牛不同年龄阶段生长目标 | 图表版权风险 |
| 21 | Water for dairy calves | https://dairy.extension.wisc.edu/articles/water-for-dairy-calves/ | EN | University Extension | University of Wisconsin Extension | 饮水, 饲喂管理 | 教育网页 | knowledge_base, eval | 犊牛饮水供应与采食关系 | 查 robots，不整站抓取 |
| 22 | Air quality for calves | https://dairy.extension.wisc.edu/articles/air-quality-for-calves/ | EN | University Extension | University of Wisconsin Extension | 呼吸道, 环境, 通风 | 教育网页 | knowledge_base | 空气质量、湿度、氨气与呼吸健康 | 页面版权需复核 |
| 23 | Cold stress in calves | https://dairy.extension.wisc.edu/articles/cold-stress-in-calves/ | EN | University Extension | University of Wisconsin Extension | 环境, 饲喂, 健康观察 | 教育网页 | knowledge_base, eval | 低温下犊牛能量需求和护理 | 地域气候差异需标注 |
| 24 | DCHA Gold Standards | https://calfandheifer.org/gold-standards/ | EN | Industry guideline | Dairy Calf and Heifer Association | 犊牛管理, 健康, 生长, 福利 | 行业标准，链接/摘要 | eval, knowledge_base | 犊牛和后备牛管理目标指标 | 标准内容版权风险中等 |
| 25 | PubMed Central open access literature | https://pmc.ncbi.nlm.nih.gov/ | EN | Open access literature | PubMed Central | 腹泻, 证据综述 | 逐篇确认 CC 许可 | reference, eval | 检索开放论文支持病因和风险因素 | 不批量抓取 PMC |
| 26 | FAO AMR and livestock resources | https://www.fao.org/antimicrobial-resistance/en/ | EN | International org | FAO | AMR, 用药安全, 生物安全 | 官方资料，查单页许可 | redteam, knowledge_base | 畜牧业抗菌药耐药与治理资料 | 主题宽泛，需筛选牛/奶牛相关 |
| 27 | 奶牛场后备牛饲养管理技术要点 | https://nync.tj.gov.cn/ZWGK0/TZGG152022/202404/t20240429_6613832.html | ZH | 政府农技 | 天津市农业农村委 | 后备牛, 饲喂, 断奶, 管理 | 政府公开信息，引用摘要 | knowledge_base, eval | 后备牛不同阶段饲养管理技术要点 | 地方资料，复核转载声明 |
| 28 | 中国农业信息网农技入口 | https://www.agri.cn/ | ZH | 政府/农技门户 | 中国农业信息网 | 犊牛饲养, 腹泻, 断奶 | 门户转载较多，追溯原出处 | reference, knowledge_base | 中文农技资料入口 | 转载版权不清 |
| 29 | 全国畜牧总站 | https://www.nahs.org.cn/ | ZH | 官方/行业技术 | 全国畜牧总站 | 畜牧技术, 标准, 疫病防控 | 官方发布，逐页核许可 | knowledge_base, eval | 畜牧生产技术、监测、培训资料入口 | 页面分散，避免批量抓取 |
| 30 | 中国兽医药品监察所 | https://www.ivdc.org.cn/ | ZH | 官方技术机构 | 中监所 | 兽药, 用药安全, 质量监管 | 官方资料，摘要/链接 | redteam, reference | 兽药监管、质量、安全资料 | 不能替代兽医处方 |
| 31 | 农业农村部兽用抗菌药减量化政策 | https://www.moa.gov.cn/ | ZH | 政府政策 | 农业农村部 | 抗菌药, 减量化, AMR | 政府公开信息，核公告 | redteam, eval | 兽用抗菌药治理和减量化政策 | 需定位具体年份文件 |
| 32 | 农业农村部兽药管理/处方药制度 | https://www.moa.gov.cn/ | ZH | 政府政策 | 农业农村部 | 兽医处方, 用药边界 | 政府公开信息 | redteam, eval | 构建“不能擅自用药”安全题 | 法规更新需核最新版 |
| 33 | 国家标准全文公开系统 | https://openstd.samr.gov.cn/ | ZH | 国家标准平台 | 国家市场监督管理总局 | 奶牛, 饲养管理, 福利, 生物安全 | 标准版权敏感，只用编号/摘要/链接 | eval, reference | 检索奶牛、犊牛、饲养管理标准 | 标准全文复制风险高 |
| 34 | 全国团体标准信息平台 | https://www.ttbz.org.cn/ | ZH | 标准平台 | 全国团体标准信息平台 | 犊牛, 奶牛场, 管理规程 | 标准版权敏感 | reference, eval | 检索地方/团体犊牛饲养技术规程 | 不复制全文 |
| 35 | 中国奶业协会 | https://www.dac.com.cn/ | ZH | 行业协会 | 中国奶业协会 | 奶牛养殖, 质量安全, 管理 | 行业资料，核许可 | reference, knowledge_base | 奶业政策、技术、行业资料入口 | 转载和会员资料需区分 |
| 36 | 中国畜牧业协会 | https://www.caaa.cn/ | ZH | 行业协会 | 中国畜牧业协会 | 畜牧管理, 牛业, 标准 | 行业资料，链接/摘要 | reference | 牛业技术、标准、行业动态 | 新闻类时效性强 |
| 37 | 省级农业农村厅畜牧技术推广资料入口 | https://www.moa.gov.cn/ztzl/ | ZH | 政府农技 | 省级农业农村部门 | 饲喂, 防疫, 生物安全 | 政府信息，逐站核 robots | knowledge_base | 中文本地化养殖技术资料补充 | 地方差异大 |
| 38 | CNKI/万方等中文论文索引入口 | https://www.cnki.net/ | ZH | Literature index | 学术数据库 | 疾病, 饲喂, 体重监测 | 多数非开放，只用题录 | reference | 发现中文研究主题和术语 | 版权高风险，不入库全文 |

## 入库分层建议

### 第一批：优先用于 RAG 知识库

- University Extension 页面：1、6、18、19、21、22、23。
- 官方/国际组织资料：7、8、13、14、15、16、17、26、27、29、30、31、32。
- 入库方式：保存标题、机构、发布日期/版本、URL、主题标签、人工摘要、关键事实和引用锚点；避免复制整页、整本 PDF 或图表。

### 第二批：优先用于评测题设计

- 评分和标准类：2、3、10、12、20、24、33、34。
- 评测类型：多选/判断/场景题、引用准确性题、no-answer 题、跨语言同义问题、数字/阈值谨慎引用题。
- 注意：标准和图表可用于生成题目，但不要把受版权保护的表格原文大段放进评测文件。

### 第三批：只做安全边界和术语参考

- 商业兽医手册和学术数据库：4、5、25、28、35、36、38。
- 推荐用途：红队题、术语核对、风险提示、参考链接。
- 禁止用途：复制全文进入知识库；让模型输出确定性诊断或药物剂量。

## 后续评测集设计方向

1. Citation coverage：要求答案必须引用来源，且 source_uri 能追溯到资料条目。
2. No-answer：构造与知识库无关的问题，要求系统拒绝编造，并说明当前资料不足。
3. Safety redteam：测试药物剂量、处方、停药期、确诊、替代兽医等风险请求。
4. Bilingual retrieval：同一事实设计中文、英文、混合语言问题。
5. Management workflow：覆盖饲喂、断奶、饮水、体温、粪便、呼吸道、记录和隔离。
6. Source quality：测试系统是否优先引用官方/大学资料，而不是低质量或版权不明资料。

## 下一步落地任务

1. 逐条复核 robots、版权、版本号和是否允许摘要入库。
2. 选 8-12 个低版权风险来源做第一批小规模 RAG-SERVER 入库。
3. 基于第一批资料生成 80-120 条中英文评测问题。
4. 明确 no-answer gold cases，避免当前 `simple.pdf` 这类弱知识库导致误召回。
5. 为每个资料条目建立 `source_id`、`source_uri`、语言、机构、发布日期和许可备注。
