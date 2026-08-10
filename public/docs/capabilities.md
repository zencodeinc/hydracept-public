# Capabilities

Integrate against stable capability keys—not provider SDKs or raw model names.

## List and describe

```http
GET /v1/capabilities
Authorization: Bearer <HYDRACEPT_API_KEY>
```

```http
GET /v1/capabilities/{key}
Authorization: Bearer <HYDRACEPT_API_KEY>
```

## Invoke vs durable jobs

| Route | Use when |
|-------|----------|
| `POST /v1/capabilities/{key}/invoke` | Short synchronous work that fits in one request |
| `POST /v1/capabilities/{key}/jobs` | Work that needs retries, polling, artifacts, or receipts |

Use jobs for image, audio, and anything that should outlive a single HTTP request.

Audio capabilities (`audio.sfx.generate.v1`, `audio.voice.generate.v1`, `audio.music.generate.v1`) run on ElevenLabs through durable Temporal workflows. Set `variantCount` (1–4) in job input to request multiple takes. See [variant selection](../jobs/#select-a-variant) when you need to pick one output before the next pipeline step.

## Launch capabilities

These capabilities are documented for public launch:

<!-- docs:launch-capabilities -->

Stick to published capability keys in customer integrations.

## Example: discover image generation

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/capabilities/image.generate.v1
```

See [Durable Jobs & Receipts](../jobs/) and [Quick Start](../).

## Contract source

The public OpenAPI document is the API contract for external integrations:

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)

Integrate against that spec—not internal FastAPI schemas or private monorepo routes.
