# Durable Jobs & Receipts

Use jobs for generation that may take longer than one HTTP request. Submit once, check progress when you need to, and download the result when it is ready.

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

See [Billing](../billing/) for wallet top-up and [Capabilities](../capabilities/) for `billingModes` discovery.

## List (principal project)

```http
GET /v1/jobs
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Lists jobs for the bearer token's project. CLI: `python -m hydracept jobs list`. Use `GET /v1/projects/{id}/jobs` for the administrative/cross-project primitive.

## Poll

```http
GET /v1/jobs/{jobId}
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Jobs move through `queued` and `running` before reaching a terminal status: `succeeded`, `failed`, or `canceled`. A job can also be `awaiting_approval`, `canceling`, or `needs_attention`; handle those states according to your workflow.

Job payloads include `nextAction` (`poll`, `download`, `present_approval`, or `stop`) and `pollAfterSeconds`. If `nextAction` is `poll`, wait that many seconds and `GET` again. Do not busy-loop.

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

Receipts include the request, provider, model, cost, retries, and resulting artifacts. Use them to review a result, debug a failed run, or keep a record for your team. Related receipts can be grouped into a [run manifest](../provenance/); a stable pin can be emitted as an [AI lockfile](../provenance/).

## Sheet & Slice (image.generate.v1)

For cohesive asset packs (sprite cycles, icon families, pose sheets), submit a job with the `sheet` input. See [Image production](../image-production/) for the full contract and a 4×4 sword-swing example.

## Full contract

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)

## Related

- [Execution provenance](../provenance/)
- [Pinned Execution](../pinned-execution/)
- [Capabilities](../capabilities/)
- [Billing & plans](../billing/)
