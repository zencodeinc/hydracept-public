# Durable Jobs & Receipts

Use jobs for generation that may take longer than one HTTP request. Submit once, check progress when you need to, and download the result when it is ready. Project history also lets agents recover from failures and reuse prior outputs without making a human copy a job ID out of Studio.

Eligible **text** jobs also use [deferred processing](../deferred-processing/): Hydracept waits for the cheaper latency-tolerant provider tier and prices those calls at 50% of standard token rates. Eligible OpenAI Responses [pins](../pinned-execution/) keep the exactness path (standard processing, one logical model execution) unless you set `processing: "deferred"`. Check `features.deferredProcessing` on the capability descriptor. Invoke and stream stay on standard processing.

## Submit

```http
POST /v1/capabilities/{key}/jobs
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

Include:

- `context` — product, project, environment
- `input` — capability-specific payload
- `execution` — `executionPreference`, `billingMode` (`byok` | `managed`). **Omit `quoteId`** unless the job input is byte-for-byte the sealed quote
- `idempotencyKey` — optional; the API mints one if missing
- `execution.executionConstraints.maxDurationSeconds` — optional **provider execution** deadline in seconds after the job starts (not queue wait). `text.general.fast.v1` defaults to 120s (max 600). Queue wait uses a separate deadline. A job that never starts fails with `QueueTimeout`. A job that starts and then exceeds the provider deadline fails with `ExecutionTimeout` only if Hydracept observed the attempt end; after provider submission began, an abandoned wait is `TRANSPORT_AMBIGUOUS`. `timeoutSeconds` is accepted as an alias for the execution deadline.

Example for `image.generate.v1` (BYOK):

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "productId": "my-product",
      "projectId": "cpr_...",
      "environment": "development"
    },
    "input": { "prompt": "cute slime icon" },
    "execution": {
      "executionPreference": "automatic",
      "billingMode": "byok"
    },
    "idempotencyKey": "demo-1"
  }' \
  https://api.hydracept.com/v1/capabilities/image.generate.v1/jobs
```

Managed inference (wallet-funded) can omit `quoteId` — the API seals a retail quote at admission:

```json
"execution": {
  "executionPreference": "automatic",
  "billingMode": "managed"
}
```

See [Billing](../billing/) for wallet top-up, [Deferred processing](../deferred-processing/) for the 50% durable-text discount, and [Capabilities](../capabilities/) for `billingModes` discovery (omitted on domain and CPU capabilities).

## Find project jobs

The project-scoped history route is the public discovery surface for agents and product tooling:

```http
GET /v1/projects/{projectId}/jobs?outcome=failed&limit=10
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Supported filters are:

- `status` — any public job status such as `failed`, `succeeded`, `needs_attention`, or `canceled`
- `capabilityKey` — for example `image.generate.v1`
- `outcome=failed` — convenience filter for failed jobs
- `outcome=reusable` — succeeded jobs with at least one output artifact
- `selected=true` — jobs with an explicitly selected variant
- `limit` and `cursor` — keyset pagination

List items contain job metadata such as `jobId`, status, capability, timestamps, `artifactCount`, `errorCode`, `selectedArtifactId`, and `receiptId` when available.

**The list is deliberately prompt-free.** It never returns prompt text, request snapshots, or error messages. This lets an agent scan failures and reusable outputs without ingesting the content of every previous request. Request content is exposed only when the caller intentionally inspects one job.

MCP:

- `hydracept_jobs_find(intent="failed")`
- `hydracept_jobs_find(intent="reusable", capability_key="image.generate.v1")`

Python: `list_project_jobs(...)` / `find_project_jobs(...)` from the `hydracept` package. The ordinary `GET /v1/jobs` list remains the bearer-principal convenience view.

## Inspect one job

```http
GET /v1/jobs/{jobId}
Authorization: Bearer <HYDRACEPT_API_KEY>
```

The canonical job resource already contains the information needed to inspect or re-run a job: status, `error`, diagnostics, artifacts, `receiptId`, and `requestSnapshot` when available. There is no separate `/inspect` HTTP resource.

For coding agents, MCP `hydracept_job_inspect(job_id)` composes that job read with the sealed receipt summary and returns a reuse candidate plus a single `nextAction`. Python exposes `inspect_job(client, job_id)` for the same purpose.

If a failed job is retried, copy the canonical snapshot input but use a **new** `idempotencyKey`. On `QUOTE_MISMATCH`, also omit the stale execution `quoteId` / `estimateId` before resubmitting.

For a successful job, prefer an explicit `selectedArtifactId`. If no explicit selection exists, inspect may identify the primary or first usable artifact, but it reports that distinction rather than pretending the artifact was human-selected.

## Poll

```http
GET /v1/jobs/{jobId}
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Jobs move through `queued` and `running` before reaching a terminal status: `succeeded`, `failed`, or `canceled`. A job can also be `awaiting_approval`, `canceling`, or `needs_attention`; handle those states according to your workflow.

Job payloads include `nextAction` (`poll`, `download_artifacts`, `retry_new`, `present_approval`, `inspect_error`, or `stop`), `retry` (`sameKey`, `newKeySafe`), and `pollAfterSeconds`. If `nextAction` is `poll`, wait that many seconds and `GET` again. Do not busy-loop. A client poll timeout is not a Hydracept failure: keep `GET /v1/jobs/{jobId}` or `POST` the **same** `idempotencyKey` while status is `queued` or `running`. Minting a new key starts a second job. Same key plus the same payload always returns the existing job, including after `failed`. `409` is only for a different payload on that key. Follow `nextAction`: mint a new key only when it is `retry_new` (`retry.newKeySafe: true`). If the code is `TRANSPORT_AMBIGUOUS`, `newKeySafe` is false — do not start a second provider attempt.

Once a known ID is lost, use project history rather than asking a human to recover it manually.

Jobs may include a `variantSet` when the capability accepts `variantCount` in input (image and audio generation). Each variant is a separate artifact with `variantIndex` on the job payload. `variantSet` reports `requestedCount`, `completedCount`, `failedCount`, and `selectedArtifactId`.

## Select a variant

When a job produced multiple variants, pick the one your pipeline should treat as the primary output:

```http
POST /v1/jobs/{jobId}/variants/select
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

```json
{ "artifactId": "art_..." }
```

The job’s `selectedArtifactId` and artifact `selected` flags update immediately. Download the chosen artifact with `GET /v1/jobs/{jobId}/artifacts/{artifactId}`.

Example for `audio.sfx.generate.v1` with two variants:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "productId": "my-product",
      "projectId": "cpr_...",
      "environment": "development"
    },
    "input": {
      "prompt": "metal button click",
      "durationMs": 500,
      "variantCount": 2
    },
    "execution": { "executionPreference": "automatic" },
    "idempotencyKey": "sfx-variants-1"
  }' \
  https://api.hydracept.com/v1/capabilities/audio.sfx.generate.v1/jobs
```

Optional control routes (when enabled for your plan):

- `POST /v1/jobs/{jobId}/cancel`
- `POST /v1/jobs/{jobId}/approve`
- `POST /v1/jobs/{jobId}/reject`

## Artifact / output

Succeeded jobs expose outputs and artifacts on the job resource. Download individual artifacts with:

```http
GET /v1/jobs/{jobId}/artifacts/{artifactId}
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Public receipts emit SHA-256 as hex. Older jobs may still advertise `sha256:<hex>` — compare the hex digest only. `HydraceptWorkspace.jobs.run(..., download_dir=...)` (CLI 0.3.1+) strips the prefix. Audio SFX artifacts are Ogg files (`filename` ends in `.ogg`), not WAV.

## Receipt

```http
GET /v1/jobs/{jobId}/receipt
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Receipts include the request, provider, model, cost, retries, and resulting artifacts. Funding and billing mode on the receipt come from admission evidence. Missing evidence stays `unknown` — do not display that as BYOK or managed trial. Use receipts to review a result, debug a failed run, or keep a record for your team. Related receipts can be grouped into a [run manifest](../provenance/); a stable pin can be emitted as an [AI lockfile](../provenance/).

## Sheet & Slice (image.generate.v1)

For cohesive asset packs (sprite cycles, icon families, pose sheets), submit a job with the `sheet` input. See [Image production](../image-production/) for the full contract and a 4×4 sword-swing example.

## Full contract

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)

## Related

- [Execution provenance](../provenance/)
- [Pinned Execution](../pinned-execution/)
- [Capabilities](../capabilities/)
- [Billing & plans](../billing/)
