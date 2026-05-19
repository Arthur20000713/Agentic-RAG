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

## Transformers 直连配置示例

对于 RTX 3060 Laptop 6GB 显存，建议先使用 0.5B 级别模型，只接管 `query_normalization`。当前推荐默认模型：

```yaml
local_model:
  enabled: true
  provider: transformers
  endpoint:
  model: Qwen/Qwen2.5-0.5B-Instruct
  timeout_seconds: 8
  max_retries: 1
  allow_final_answer: false
  device: auto
  torch_dtype: auto
  max_new_tokens: 128
  temperature: 0

model_router:
  enabled: true
  shadow_mode: false
  allow_low_risk_takeover: true
  takeover_task_types:
    - query_normalization
```

安装可选依赖：

```powershell
.venv\Scripts\python.exe -m pip install -e ".[transformers]"
```

`provider=transformers` 当前只支持 `query_normalization`。其它结构化任务会返回结构化 fallback，不会静默伪装成真实模型成功。模型第一次运行可能会从 Hugging Face 下载权重；需要离线运行时，应先手动下载模型并把 `model` 配置为本地目录。

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
