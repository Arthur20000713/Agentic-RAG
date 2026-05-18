# V5 ModelRouter 接管策略

V5.1 允许本地模型在低风险结构化任务中 takeover，但 Safety 和 final guard 仍是最终边界。

## 允许接管

- `query_normalization`
- `structured_extraction`
- `measurement_analysis`
- `summarization`

接管还必须同时满足：

- `v3.enabled=true`
- `model_router.enabled=true`
- `model_router.shadow_mode=false`
- `model_router.allow_low_risk_takeover=true`
- `local_model.enabled=true`
- safety level 属于 `S0`、`S1` 或 `S2`
- `requires_final_answer=false`

## 禁止接管

- `S3`、`S4` 高风险任务。
- `requires_final_answer=true` 的请求。
- 处方、药物剂量、停药期、确诊、替代兽医等高风险回答。
- 未在 `model_router.takeover_task_types` 中显式配置的任务。

## 回退

本地模型输出 schema 不合格时必须回退规则路径或 primary 路径，并记录：

- `fallback_required`
- `fallback_reason`
- `route_mode`
- `selected_model`
- `model_version`
- `latency_ms`

## 评测

```powershell
.venv\Scripts\python.exe scripts\run_eval.py --mode v5 --optional --output-dir reports\v5_router
```

报告输出 `takeover_rate`、`fallback_rate`、`blocked_high_risk_count` 和逐 case 路由结果。该评测不要求真实本地模型 endpoint 可用，只验证 V5 Router 策略和安全边界。
