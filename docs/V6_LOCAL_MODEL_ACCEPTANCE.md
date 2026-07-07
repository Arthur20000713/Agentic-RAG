# V6 Local Model Acceptance

## Scope

V6.5 accepts the local model path for `query_normalization` only.
The local model is configured as a shadow-capable structured-task model and must not generate final user-facing answers.

## Default Configuration

`config/settings.yaml`:

```yaml
v3:
  enabled: true
model_router:
  enabled: true
  shadow_mode: true
  allow_low_risk_takeover: false
local_model:
  enabled: true
  provider: transformers
  model: Qwen/Qwen2.5-0.5B-Instruct
  timeout_seconds: 60
  max_retries: 1
  allow_final_answer: false
  device: auto
  torch_dtype: auto
  max_new_tokens: 96
  temperature: 0
```

## Hardware Acceptance

- GPU: NVIDIA GeForce RTX 3060 Laptop GPU, 6 GB VRAM
- PyTorch: `2.12.1+cu130`
- CUDA visible to PyTorch: `true`
- Transformers: `5.13.0`
- Accepted task: `query_normalization`

Tracked acceptance evidence:

- `docs/local_model/transformers_smoke_report.json`

Runtime report:

```powershell
.venv\Scripts\python.exe scripts\doctor_v6.py --json
```

Expected local model check:

- `local_model_acceptance.status=passed`
- `provider=transformers`
- `model=Qwen/Qwen2.5-0.5B-Instruct`
- `query_normalization_smoke=passed`

## Verification Commands

```powershell
.venv\Scripts\python.exe -c "import torch, transformers; print(torch.__version__, torch.cuda.is_available(), transformers.__version__)"
.venv\Scripts\python.exe scripts\run_local_model_smoke.py --optional --output reports\local_model_v6_transformers_smoke.json
.venv\Scripts\python.exe scripts\check_v6.py --stage full
```

The smoke command must return `PASSED: local model smoke provider=transformers`.
`skipped` is not accepted as V6.5 evidence.

## Safety Boundary

- `model_router.shadow_mode=true` keeps primary application behavior in control.
- `model_router.allow_low_risk_takeover=false` prevents automatic takeover.
- `local_model.allow_final_answer=false` prevents local model final-answer generation.
- RAG remains real by default through `rag_server.query_mode=real`.
