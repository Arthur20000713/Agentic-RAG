# 安全规则初稿

V1 输出边界：

- 不输出具体药物剂量。
- 不给出确定性诊断。
- 疾病、疫情、食品安全相关回答最终返回前必须经过 Final Safety Guard。
- RAG-SERVER 不可用、超时或低置信时，不伪造检索结果和引用。
- 体尺异常结论必须有数值依据；无历史数据时不能判断增长趋势。

当前规则实现：

- `dosage`：拦截 `mg/kg`、`mg`、`ml`、`g`、`kg`、`毫升`、`克`、`片` 等具体剂量表达。
- `definitive_diagnosis`：拦截“确诊”“确定诊断”等确定性诊断表达。
- `prescription`：拦截处方类输出。
- `fabricated_tool_result`：拦截工具或检索失败后仍声称有检索结果的表达。

`FinalSafetyGuard` 在发现违规时返回保守安全提示，不保留具体剂量或确定性诊断内容。

Agent Workflow 要求：

- 疾病问诊最终回答必须经过 `FinalSafetyGuard`。
- Verifier-lite 会检查专业回答缺引用、剂量违规、体尺异常缺 evidence。
- 追问分支不得调用 RAG，不得伪造引用。

## V5 local model boundaries

- `local_model.allow_final_answer` must remain `false` by default.
- Local-model takeover is limited to low-risk structured tasks: query normalization, slot extraction, measurement analysis, and summarization.
- Safety levels `S3` and `S4` require the primary guarded path and must not be answered by `local_small`.
- Final-answer, prescription, dosage, withdrawal-period, and definitive-diagnosis requests must be blocked or routed to the primary guarded path.
- If a local model returns invalid JSON, invalid schema, timeout, or tool error, the system must fall back to deterministic rules or the primary path and record the fallback reason.
- LoRA inference is allowed only when a registered adapter is active and has `safety_gate_status=passed`.

V5 does not add multi-user permission control, internet production deployment, or production incident monitoring. These remain out of scope.
