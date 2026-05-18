# V5 本地模型接入指南

V5.0 支持真实本地模型后端接入，但默认仍保持关闭。`provider=mock` 只用于测试和旧路径兼容，不能作为真实本地模型验收证据。

## 默认配置

默认 `config/settings.yaml` 保持：

```yaml
local_model:
  enabled: false
  provider: mock
  endpoint:
  model:
  timeout_seconds: 3
  max_retries: 0
  allow_final_answer: false
```

`allow_final_answer` 默认必须为 `false`。本地模型只允许进入低风险结构化任务，不能直接接管高风险兽医结论、处方、剂量、停药期或最终回答。

## Ollama 配置示例

用户确认本地模型服务可用后，可以在本地配置中启用：

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

本仓库不会自动下载模型，也不会启动外部模型服务。缺少 endpoint、model 或本地运行环境时，检查脚本必须 skipped 或失败，不能回退到 mock 并伪装成真实能力。

## 检查命令

静态 V5 检查：

```powershell
.venv\Scripts\python.exe scripts\check_v5.py --stage full
```

本地模型专项检查：

```powershell
.venv\Scripts\python.exe scripts\check_v5.py --stage local-model
```

独立 optional smoke：

```powershell
.venv\Scripts\python.exe scripts\run_local_model_smoke.py --optional --output reports\local_model_smoke.json
```

未配置真实本地模型时，optional smoke 会写入 `status=skipped`，这只说明本地模型环境不可用，不能作为 V5 真实本地模型通过证据。
