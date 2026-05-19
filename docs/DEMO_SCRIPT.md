# V2 演示脚本

## 0. 演示前准备

启动后端：

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开页面：

```text
http://127.0.0.1:8000/app
```

可选检查：

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server"
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports\fake
.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
```

如要演示真实 RAG-SERVER，先配置：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
```

说明话术：默认演示使用 fake RAG 回归链路，保证不依赖外部服务；真实 RAG 必须显式配置，不会静默降级成 fake。

## 1. Chat 知识问答

页面：`/app` 的 Chat 区域。

输入：

```text
How should cattle feeding be managed?
```

预期展示：

- `answer` 中包含带引用的畜牧业回答。
- Sources 区域展示 `source_uri`、标题、页码或章节。
- Tools 区域包含 `livestock_rag_search`、`verifier_agent`、`safety_agent`、`response_agent`。
- Debug JSON 中能看到 `request_id`、`intent`、`sources`、`tools_used`。

讲解重点：

- RAG Agent 只使用检索结果生成带引用回答。
- `source_uri` 是引用、trace、verifier、eval 共用的稳定来源 ID。
- Verifier 和 Safety 在最终响应前执行。

## 2. 疾病问诊追问

在 Chat 区域输入：

```text
牛拉稀了怎么办？
```

预期展示：

- `intent` 为 `disease_consultation`。
- 回答不是直接给诊断或用药，而是提出最多 3 个追问。
- 追问应覆盖持续时间、体温、是否群体发病或主要症状等缺失槽位。
- Tools 区域包含 `slot_extractor`、`safety_agent`、`response_agent`，但不应调用 `livestock_rag_search`。

继续在同一 session 中补充：

```text
犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病
```

预期展示：

- 疾病图进入高风险评估路径。
- 调用 `livestock_rag_search` 获取处理原则。
- 回答包含风险等级、是否建议联系兽医、证据引用和安全提示。

讲解重点：

- V2.4 的 session context 支持多轮续接。
- 高风险结论仍是辅助建议，不替代兽医诊断。
- 缺证据或信息不足时不会编造处方。

## 3. 高风险安全边界

演示方式：说明高风险用药、确定性诊断、具体剂量会被 Safety Agent 拦截。

可使用评测命令展示：

```powershell
.venv\Scripts\python.exe -m pytest tests\integration\test_eval_runner.py -k multi_agent
```

讲解重点：

- `high_risk_refusal` 用例会注入不安全草稿。
- Safety Agent 会把具体剂量和确定诊断改写成安全提示。
- 这条链路用于证明安全边界是工程约束，不是提示词承诺。

## 4. 体尺报告

切换到 Measurement 区域。

输入示例：

```text
animal_id: yak_032
chest_girth_cm: 158.4
confidence: 0.82
use_demo_history: true
```

预期展示：

- 报告包含 `summary`、`abnormal_items`、`evidence`、`recommendation`。
- 如果使用 demo history，报告应明确说明演示数据不代表真实个体记录。
- Tools 区域或 Debug JSON 中包含 `body_measurement_analyzer`，不应依赖 RAG。

讲解重点：

- 体尺报告是结构化业务工具，不走知识库检索。
- 异常项必须有数值依据。
- 无历史时只描述当前值，不虚构增长趋势。

## 5. Debug Panel 和 Trace

演示 Debug JSON：

- 查看最近一次 API 响应的完整 JSON。
- 核对 `request_id`、`rag_mode`、`agent_path`、`safety`、`verifier`。
- 打开 Swagger：`http://127.0.0.1:8000/docs`，查询 `/api/rag/status` 和 `/api/traces/{request_id}`。

预期讲法：

- Debug Panel 不是用户说明书，而是面试演示和排障面板。
- `agent_path` 解释为什么系统走了 RAG、Disease 或 Measurement 路径。
- RAG trace 和 agent trace 可用于定位失败是检索、映射、验证还是安全拦截。

## 6. 评测报告展示

推荐演示命令：

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --mode fake --output-dir reports\fake
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real
.venv\Scripts\python.exe scripts\run_eval.py --mode multi_agent --golden-set tests\fixtures\golden_set.json --output-dir reports\multi_agent
```

展示文件：

- `reports\fake\eval_summary.md`
- `reports\real\eval_summary.md`
- `reports\real\failure_analysis.md`
- `reports\multi_agent\eval_summary.md`

讲解重点：

- fake eval 用于稳定回归，不说明真实知识库质量。
- real eval 用于真实 RAG 质量定位，未配置时输出 skipped report。
- multi-agent eval 计算 route、agent path、safety、trace 指标。

## 7. 收尾说明

可以用以下三句话结束：

1. V2 的重点不是重写 RAG，而是把已有 RAG-SERVER 产品化接入到畜牧业业务闭环。
2. Multi-agent 采用固定图，路径可解释、可测试、可 trace。
3. fake、real、multi-agent eval 分层，既保证本地回归稳定，又能定位真实 RAG 质量问题。

## 8. V5 本地优先演示补充

V5 演示重点是本地模型、Router takeover、LoRA 闭环和发布检查。

推荐先运行默认离线检查：

```powershell
.\scripts\check_release_v5.ps1 -OutputDir .tmp_tests\v5_release_demo
```

展示点：

- `scripts\run_eval.py --mode v5` 输出低风险 takeover、fallback、高风险阻断和质量门禁指标。
- `v3_debug.model_fallbacks` 可以展示本地模型结构化输出失败后的回退原因。
- `config/settings.v5.example.yaml` 展示真实 RAG、本地模型、LoRA 和 Router takeover 的推荐配置。
- `local_model.provider=mock` 只用于测试，不是产品级本地模型证据。
- LoRA 没有真实 adapter 时只能展示数据脱敏、训练编排和 registry gate，不能宣称真实 LoRA 推理验收通过。

如需演示真实依赖，必须显式开启：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.\scripts\check_release_v5.ps1 -IncludeRealRag -IncludeLocalModel -OutputDir .tmp_tests\v5_release_real
```
