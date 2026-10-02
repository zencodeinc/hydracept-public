---
name: hydracept-inspect
description: >
  Read the prompt a Hydracept job executed, recover from a failure, or reuse a
  prior artifact without asking the human to paste a job id.
---

# Hydracept Inspect

Use this skill when the user asks for the prompt that was executed, what a prior job was asked, a historical prompt, a failed job, what happened to the last job, or to reuse the last good/selected output.

## Read the executed prompt

1. These tools use the workspace-bound project. Bind the project that owns the job before searching.
2. Known job id: `hydracept_job_inspect(job_id)` and read `executedPrompt`. The same text is `requestSnapshot.input.prompt`.
3. Unknown job id: `hydracept_jobs_find(intent="recent")`, then inspect that one job. The find list never includes prompt text.
4. Text jobs return `executedPrompt` when a prompt record was kept and no input payload was stored. `executedPrompt` is null when Hydracept did not keep that record (hashes-only retention, or no prompt was captured).

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
