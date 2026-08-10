# Durable Jobs & Receipts

Use durable jobs when generation should survive beyond a single HTTP request. This is the main path for image, audio, and similar work.

## Submit

```http
POST /v1/capabilities/{key}/jobs
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

Include:

- `context` — product, project, environment
- `input` — capability-specific payload
- `execution` — preferences such as `executionPreference`
- `idempotencyKey` — stable key for safe retries

Example for `image.generate.v1`:

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
    "execution": { "executionPreference": "automatic" },
    "idempotencyKey": "demo-1"
  }' \
  https://api.hydracept.com/v1/capabilities/image.generate.v1/jobs
```

## Poll

```http
GET /v1/jobs/{jobId}
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Keep polling until status is `succeeded`, `failed`, or `canceled`.

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

## Receipt

```http
GET /v1/jobs/{jobId}/receipt
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Receipts include provenance and execution evidence for audits, debugging, and pipeline bookkeeping.

## Full contract

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
