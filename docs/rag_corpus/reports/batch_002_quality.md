# Batch 002 Quality Report

- batch id: batch_002
- collection: livestock_v4_2
- source count: 10
- ingestion status: planned
- preflight status: not_run
- eval summary: not_run
- failure categories: not_run

## Scope

`batch_002` is the planned V4.2 livestock corpus batch for `livestock_v4_2`. It records planned local human-summary files under `C:\tmp\livestock_corpus\batch_002`. The files are not committed to this repository.

## Current Status

- Local corpus files: not prepared in this repository.
- RAG-SERVER ingest: not executed.
- Real RAG preflight: not run for this collection.
- Real eval: not run for this collection.
- Quality gate: not evaluated.

## Trend

- baseline: none
- reason: `batch_002` is the first planned V4.2 collection batch for `livestock_v4_2`; no previous batch report exists for this collection version.

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| pass_rate | n/a | not_run | n/a |
| no_answer_accuracy | n/a | not_run | n/a |
| source_uri_coverage | n/a | not_run | n/a |
| safety_pass_rate | n/a | not_run | n/a |

## Required Follow-Up

1. Prepare approved summary files at the paths listed in `docs/rag_corpus/batches/batch_002.yaml`.
2. Run `scripts/check_rag_corpus.py --batch docs\rag_corpus\batches\batch_002.yaml --dry-run`.
3. After user confirmation, run the generated RAG-SERVER ingest commands outside fake mode.
4. Run real preflight, real eval, and quality gate checks.
5. Replace the `not_run` fields above with measured results.
