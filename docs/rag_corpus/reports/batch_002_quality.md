# Batch 002 Quality Report

- batch id: batch_002
- collection: livestock_v4_2
- source count: 18
- ingestion status: completed
- preflight status: passed
- eval summary: 80/80 passed, pass rate 100.00%
- failure categories: none
- quality gate: passed

## Scope

`batch_002` is the V4.2 livestock corpus batch for `livestock_v4_2`. It is tracked by `docs/rag_corpus/batches/batch_002.yaml` and aligned with `docs/rag_corpus/manifests/livestock_v4_2.yaml`.

## Latest Verification

- Command: `.\scripts\check_real_batch.ps1 -Batch docs\rag_corpus\batches\batch_002.yaml -OutputDir .tmp_tests\real_rag_default_batch`
- Date: 2026-07-01
- Preflight status: passed
- Target collection: livestock_v4_2
- Manifest collection: livestock_v4_2
- RAG-SERVER collections: default, livestock_v4_2
- MCP tools: query_knowledge_hub, list_collections, get_document_summary
- Warning: RAG_COLLECTION_MISMATCH

The collection mismatch warning is expected for this local environment because the RAG-SERVER config default collection differs from the Agentic RAG target collection. Agentic RAG explicitly targets `livestock_v4_2`.

## Metrics

| Metric | Value |
|---|---:|
| total_cases | 80 |
| passed_cases | 80 |
| failed_cases | 0 |
| pass_rate | 100.00% |
| intent_accuracy | 100.00% |
| rag_call_accuracy | 100.00% |
| citation_coverage | 100.00% |
| no_answer_accuracy | 100.00% |
| safety_pass_rate | 100.00% |
| follow_up_accuracy | 100.00% |
| structure_completeness | 100.00% |
| rag_citation_coverage | 100.00% |
| source_uri_coverage | 100.00% |

## Categories

| Category | Passed | Total | Pass rate |
|---|---:|---:|---:|
| feeding_management | 12 | 12 | 100.00% |
| general_qa | 33 | 33 | 100.00% |
| high_risk_refusal | 15 | 15 | 100.00% |
| no_answer | 20 | 20 | 100.00% |

## Failure Categories

| Category | Count |
|---|---:|
| NO_COLLECTION | 0 |
| NO_RETRIEVAL_RESULT | 0 |
| LOW_RETRIEVAL_SCORE | 0 |
| NO_ANSWER_FALSE_POSITIVE | 0 |
| LOW_CONFIDENCE_ACCEPTED | 0 |
| MISSING_CITATION | 0 |
| BAD_MAPPING | 0 |
| UNSUPPORTED_CLAIM | 0 |
| SAFETY_VIOLATION | 0 |
| TOOL_TIMEOUT | 0 |
| RAG_SERVER_UNAVAILABLE | 0 |

## Mapping Warnings

| Warning | Count |
|---|---:|
| RAG_LOW_CONFIDENCE_SCORE | 1 |

## Trend

- baseline: none
- reason: `batch_002` is the first accepted quality report for the `livestock_v4_2` collection.

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| pass_rate | n/a | 100.00% | n/a |
| no_answer_accuracy | n/a | 100.00% | n/a |
| source_uri_coverage | n/a | 100.00% | n/a |
| safety_pass_rate | n/a | 100.00% | n/a |

## Recheck Command

```powershell
$env:RAG_SERVER_PATH="C:\Users\DELL\PycharmProjects\PythonProject\RAG-SERVER"
.\scripts\check_real_batch.ps1 -Batch docs\rag_corpus\batches\batch_002.yaml -OutputDir reports\real_v4_2_batch
```
