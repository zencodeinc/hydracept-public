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

Each capability descriptor includes **`billingModes`** and **`pricing`** so you can discover BYOK vs managed availability and whether an estimate is required before submitting:

```json
{
  "key": "image.generate.v1",
  "billingModes": {
    "byok": { "available": true },
    "managed": { "available": true, "serviceFeeBps": 1500 }
  }
}
```

- **BYOK** — use your provider credentials (0% Hydracept inference fee). See [Connections](../connections/).
- **Managed** — PAYG wallet + Hydracept service fee (`serviceFeeBps` / 100 = percent). See [Billing](../billing/).

## Quote is optional preview

Call `/quote` for a firm 0.3 retail quote (`pricing.quote`, `kind: estimate`) in the account billing currency. Quotes **do not reserve or charge** funds. **Do not** attach a stale `quoteId` on submit — omit `execution.quoteId` and the API seals a matching quote at admission. Reusing a quote whose fingerprint no longer matches the job body returns `409 QUOTE_MISMATCH`. `POST .../estimate` is the same 0.3 response.

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

Pass the returned `quoteId` on job submit as `execution.quoteId` only when the job body is unchanged. Execution remeasures pricing inputs against the sealed quote; a mismatch fails before work starts. `estimateId` is accepted as an inbound alias of `quoteId`.

## Invoke vs durable jobs

| Route | Use when |
|-------|----------|
| `POST /v1/capabilities/{key}/invoke` | Short synchronous work that fits in one request |
| `POST /v1/capabilities/{key}/jobs` | Work that needs retries, polling, artifacts, or receipts |

Use jobs for image, audio, 3D mesh, and any generation that may take longer than one HTTP request.

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

## Image production

`image.generate.v1` supports transparent output, Sheet & Slice, and variants. See [Image production](../image-production/).

## Contract source

The public OpenAPI document is the API contract for external integrations:

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)

Use that public spec as the source of truth for integrations.
