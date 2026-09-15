# Capabilities

A capability key is a stable name for an outcome, such as image generation or voice generation. Use it to integrate once instead of building a separate provider integration for every workflow.

## List and describe

```http
GET /v1/capabilities
Authorization: Bearer <HYDRACEPT_API_KEY>
```

```http
GET /v1/capabilities/{key}
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Anonymous discovery is intentionally conservative. It advertises capabilities that are safe to present before Hydracept has account and approval context. Account-scoped or mutating infrastructure actions, such as domain registration and DNS changes, are discoverable after authentication in Studio and through authenticated capability surfaces rather than in the anonymous first-contact catalog.

Inference capability descriptors include **`billingModes`**, **`pricing`**, and factual **execution** / **output** fields so an agent can decide whether a call is usable right now — without reading several docs pages. Domain, DNS, and CPU-processing capabilities omit `billingModes`; they are not inference-priced. Registrar custody uses `credentialSources` instead.

```json
{
  "key": "image.generate.v1",
  "readySummary": "Ready now · managed execution · quote available",
  "execution": {
    "oneShot": true,
    "managedAvailable": true,
    "providerSetupRequired": false,
    "projectLocalRequired": false,
    "estimateAvailable": true,
    "trialEligible": true
  },
  "funding": {
    "mode": "managed_trial",
    "eligible": true,
    "status": "ready"
  },
  "output": { "kind": "artifact", "mediaType": "image/png" },
  "interaction": { "typicallyRequired": false },
  "billingModes": {
    "byok": { "available": true },
    "managed": { "available": true, "serviceFeeBps": 600 }
  }
}
```

Find by task: `GET /v1/capabilities?q=generate+an+image` or `python -m hydracept capabilities find "generate an image"`.

- **oneShot** — this capability can be invoked without a product integration commitment
- **managedAvailable** — no provider account is required for this call when true
- **trialEligible** — managed first-use policy may cover this capability (server-authoritative remaining balance is on authenticated `funding`)
- **funding.status** — `ready` or `funding_required` (with `fundingOptions`: managed, BYOK). Do not treat an unbound provider as "cannot execute" when managed first-use remains.
- **readySummary** — agent-readable readiness (not a usefulness score)
- **BYOK** — use your provider credentials (0% Hydracept inference fee). See [Connections](../connections/).
- **Managed** — PAYG wallet + Hydracept service fee (`serviceFeeBps` / 100 = percent). See [Billing](../billing/).

## Quote is optional preview

Call `/quote` when you want to inspect the customer price before execution. The quote is a preview (`pricing.quote`, `kind: estimate`): it does **not** reserve or charge funds. Normal job submission should omit `execution.quoteId`; the API measures the submitted job and seals its retail quote at admission.

```http
POST /v1/capabilities/image.generate.v1/quote
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

```json
{
  "input": { "prompt": "cute slime icon", "model": "auto" },
  "billingMode": "managed"
}
```

If a workflow deliberately binds execution to a previously returned quote, the submitted job body must be unchanged and `execution.quoteId` may reference that quote. Execution remeasures pricing inputs against the sealed quote; a mismatch fails before work starts with `409 QUOTE_MISMATCH`. Never attach a stale quote ID just because a quote was requested earlier. `estimateId` is accepted as an inbound alias of `quoteId`.

## Invoke vs durable jobs

| Route | Use when |
|-------|----------|
| `POST /v1/capabilities/{key}/invoke` | Short synchronous work that fits in one request |
| `POST /v1/capabilities/{key}/jobs` | Work that needs retries, polling, artifacts, or receipts |

Use jobs for image, audio, 3D mesh, and any generation that may take longer than one HTTP request.

`text.general.fast.v1` still offers `invoke_sync`, but that path is edge-held: about **60 seconds / 2048 `maxOutputTokens`**. Larger completions (including 8192-token title cards) must use `POST /v1/capabilities/text.general.fast.v1/jobs`. Catalog `features.syncInvoke` and `features.durableJob` document those envelopes separately. Durable jobs share the durable-text worker; concurrency is hardware-bounded so one job does not block another of the same variety. `executionConstraints.maxDurationSeconds` is the **provider execution** deadline after the job starts (default **120s**, max **600**), not queue wait. Queue timeout, execution timeout, and post-submit ambiguity are different error codes (`QueueTimeout`, `ExecutionTimeout`, `TRANSPORT_AMBIGUOUS`).

Durable text jobs (`executionModes` includes `job_async`) on eligible models also use **deferred processing**: Hydracept waits for the cheaper latency-tolerant provider tier and charges **50% of standard token rates**. Check `features.deferredProcessing` on the capability descriptor, or read [Deferred processing](../deferred-processing/). Synchronous invoke and stream stay on standard processing.

Audio capabilities (`audio.sfx.generate.v1`, `audio.voice.generate.v1`, `audio.music.generate.v1`) run as durable jobs. Artifacts are **Ogg** (`audio/ogg`) with a `.ogg` filename, not WAV. Set `variantCount` (1–4) in job input to request multiple takes. See [variant selection](../jobs/#select-a-variant) when you need to pick one output before the next pipeline step.

`image.generate.v1` width and height snap up to multiples of 16 (Open Graph 1200×630 becomes 1200×640).

3D capabilities (`model.generate.3d.v1`, `model.generate.3d.from-image.v1`) run on Meshy. Use `model.generate.3d.v1` when you have turnaround view artifacts; use `model.generate.3d.from-image.v1` to chain OpenAI turnaround generation from a single concept image. See [5-minute 3D asset](../five-minute-3d-asset/).

## Available capabilities

Discover the live catalog with `GET /v1/capabilities` or `python -m hydracept agent-context`. Launch scope is the launch gate, not a frozen README list.

Use the published capability keys from that catalog in your integrations.

## Example: discover image generation

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/capabilities/image.generate.v1
```

See [Durable Jobs & Receipts](../jobs/) and [Quick Start](../).

## Prompt limits

Hydracept **never silently truncates** a caller prompt to fit a provider limit. Overflow is rejected **before** quote, wallet reservation, or provider submission (`422` / `PromptTooLong`).

Read `inputConstraints` on `GET /v1/capabilities/{key}` — not provider docs — for the effective measurement, max, overflow policy, and per-model overlays (`byModel`). JSON Schema `maxLength` is a coarse ceiling; the selected model's `byModel` entry is authoritative when present.

Examples:

- `audio.sfx.generate.v1` prompt: 450 characters, `overflow: reject`
- `audio.voice.generate.v1` text: 10,000 characters for Multilingual v2; 40,000 for Flash/Turbo v2.5
- `audio.music.generate.v1` prompt: 4,100 characters
- `image.generate.v1` prompt: 32,000 characters for GPT Image 1/2 (`byModel`)

See [Errors](../errors/).

## Image production

`image.generate.v1` supports transparent output, Sheet & Slice, and variants. See [Image production](../image-production/).

## Contract source

The public OpenAPI document is the API contract for external integrations:

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)

Use that public spec as the source of truth for integrations.
