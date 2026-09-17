---
name: hydracept-inspect
description: >
  Recover from Hydracept job failures and reuse prior successful artifacts without
  asking the human to paste a job id.
---

# Hydracept Inspect

Use this skill when the user says a Hydracept job failed, asks what happened to the last job, or asks to reuse the last good/selected output.

## Workflow

1. Find the job instead of asking for an id:
   - failure: `hydracept_jobs_find(intent="failed")`
   - reuse: `hydracept_jobs_find(intent="reusable", capability_key="...")`
   - recent context: `hydracept_jobs_find(intent="recent")`
2. Inspect the chosen item with `hydracept_job_inspect(job_id)`.
3. For failure, read `error.code`, `diagnostics`, and the receipt summary. Do not guess from provider strings or previews.
4. For a retry, copy the canonical `requestSnapshot` input, remove the old `idempotencyKey`, and submit with a new idempotency key. On `QUOTE_MISMATCH`, also omit stale `execution.quoteId` / `estimateId`.
5. For reuse, prefer `selectedArtifactId` / `reuseCandidateArtifactId`. If no explicit selection exists, the inspect bundle may nominate the primary/first artifact but must report `reuseCandidateSelected=false`.
6. Download the artifact or pass it as a reference to the next capability job. Do not silently approve, favorite, or promote it.

## Public history contract

`GET /v1/projects/{projectId}/jobs` is project- and environment-scoped and deliberately prompt-free. Supported filters include:

- `status=<public job status>`
- `capabilityKey=<capability key>`
- `outcome=failed`
- `outcome=reusable` (succeeded with at least one output artifact)
- `selected=true` (explicit variant selection exists)

List items may include `errorCode`, `selectedArtifactId`, and `receiptId`, but never prompt text or error messages. Prompt/request content is only exposed when intentionally inspecting one job through `GET /v1/jobs/{jobId}` / `hydracept_job_inspect`.

## Boundaries

- Do not ask the human for a job id before trying `hydracept_jobs_find`.
- Do not use Studio Prompt Memory, reviews, or `JobSurfaceMetadata.favorite` as history authority.
- Do not infer PNG alpha correctness from vision; use `transparencyReport` or `python -m hydracept verify <path.png> --json`.
- Pinned research execution remains separate: use `hydracept_pinned_get` by id. Do not pretend project job history is a pinned-run history API.
- If no project is bound, use `hydracept_status` / `python -m hydracept init`; never invent a project id.
- Inspection is read-only. Re-running always creates a new attempt with a new idempotency key.
