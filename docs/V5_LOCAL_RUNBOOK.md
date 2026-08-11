# V5 本地运行手册

本手册用于本地验收 V5：真实 RAG、本地模型、LoRA 灰度推理和 ModelRouter 低风险接管。默认配置仍保持保守，缺少真实依赖时检查脚本会返回 `skipped` 或失败原因，不能静默退回 fake 并当作通过。

## 1. 基础检查

```powershell
.venv\Scripts\python.exe scripts\check_v5.py --stage full
```

该命令只检查 V5 静态契约和离线路径，不要求 RAG-SERVER、Ollama 或 LoRA adapter 可用。

## 2. 真实 RAG

推荐配置见 `config/settings.v5.example.yaml`：

```yaml
rag_server:
  query_mode: real
  repo_path: C:/Users/DELL/PycharmProjects/PythonProject/RAG-SERVER
  python_executable: C:/Users/DELL/PycharmProjects/PythonProject/RAG-SERVER/.venv/Scripts/python.exe
  collection: livestock_v4_2
  timeout_seconds: 30
  strict_real_mode: true
```

运行：

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.venv\Scripts\python.exe scripts\run_eval.py --mode real --optional --output-dir reports\real_rag_v5
```

如果真实 collection 不存在，报告应明确 `skipped` 或错误码，不能切换到 fake。

## 3. 本地模型

Ollama 示例：

```yaml
local_model:
  enabled: true
  provider: ollama
  endpoint: http://127.0.0.1:11434
  model: qwen2.5:7b-instruct
  timeout_seconds: 8
  max_retries: 1
  allow_final_answer: false
```

检查：

```powershell
.venv\Scripts\python.exe scripts\run_local_model_smoke.py --optional --output reports\local_model_smoke.json
```

`--optional` 在服务不可用时会写入 skipped 报告；这只表示本地模型环境缺失，不是本地模型能力验收通过。

## 4. ModelRouter Takeover

只允许低风险结构化任务接管：

```yaml
agent_runtime:
  engine: langgraph
model_router:
  enabled: true
  shadow_mode: false
  allow_low_risk_takeover: true
  takeover_task_types:
    - query_normalization
    - structured_extraction
    - measurement_analysis
    - summarization
  blocked_safety_levels:
    - S3
    - S4
local_model:
  enabled: true
  allow_final_answer: false
```

高风险任务、最终回答、处方、剂量、停药期和确诊类请求必须阻断或回退。回退信息会进入 `model_route_log`、`tool_results.model_fallbacks` 或 `agent_runtime_debug.model_fallbacks`。

## 5. LoRA

LoRA 数据集导出和检查：

```powershell
.venv\Scripts\python.exe scripts\export_lora_dataset.py --output-dir .tmp_tests\lora_dataset
.venv\Scripts\python.exe scripts\check_lora_dataset.py --dataset-dir .tmp_tests\lora_dataset
```

训练编排默认 dry-run，不会启动真实训练：

```powershell
.venv\Scripts\python.exe scripts\train_lora_adapter.py --config config\lora_training.yaml --dry-run
```

只有注册表中 active adapter 的 `safety_gate_status=passed` 时，LoRA 才允许进入推理路径。没有真实 adapter 时，LoRA eval 可以报告 skipped，但不能作为 LoRA 真实训练完成证据。

## 6. 发布前检查

```powershell
.venv\Scripts\python.exe -m pytest -m "not rag_server and not local_model" -q
.venv\Scripts\python.exe scripts\check_v2.py --offline --frontend-contract --docs
.venv\Scripts\python.exe scripts\check_v3.py --stage full
.venv\Scripts\python.exe scripts\check_v4_2.py --stage full
.venv\Scripts\python.exe scripts\check_v5.py --stage full
.venv\Scripts\python.exe scripts\run_eval.py --mode v5 --optional --output-dir reports\v5
.venv\Scripts\python.exe scripts\check_v5.py --stage gate --report reports\v5\eval_result.json
```
