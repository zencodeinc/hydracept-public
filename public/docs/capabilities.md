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
  "readySummary": "Managed inference available · quote available",
  "execution": {
    "oneShot": true,
    "managedInferenceAvailable": true,
    "inferenceProviderSetupRequired": false,
    "projectLocalRequired": false,
    "estimateAvailable": true,
    "trialEligible": true
  },
  "funding": {
    "mode": "managed_trial",
    "eligible": true,
    "status": "catalog_available"
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

- **oneShot** — this capability can be invoked without a product integration commitment. This is a **business** property, not a transport one: it says the call is worth making on its own, not how to make it. Do not infer the HTTP path from it — **`executionModes` is the only source of truth for transport.** `image.generate.v1` is `oneShot: true` and `job_async` only: submit it to `POST /v1/capabilities/{key}/jobs` and poll `GET /v1/jobs/{id}`.
- **executionModes** — how this capability can be reached, and the only thing to read before choosing an endpoint. `invoke_sync` / `invoke_stream` mean `POST /v1/capabilities/{key}/invoke`; `job_async` means `POST /v1/capabilities/{key}/jobs`. A capability listing only `job_async` will reject `/invoke`, and vice versa.
- **managedInferenceAvailable** — catalog-level hint: no provider account is required for this inference call when true and the workspace is runnable
- **inferenceProviderSetupRequired** — a provider connection is required when true; never ask for a provider key when managed inference is available
- **trialEligible** — managed first-use policy may cover this capability (server-authoritative remaining balance is on authenticated `funding`)
- **workspaceRunnable** — authenticated caller-relative readiness. Check `workspaceRunnable.runnable` before invoking; when false, use `status` / `requiredAction` instead of treating catalog `execution` as a promise for this workspace.
- **funding.status** — catalog-level availability: `catalog_available` or `provider_required`. Caller-relative readiness (`ready`, `funding_required`, `missing_provider`) is reported by authenticated `workspaceRunnable`. Do not treat an unbound provider as "cannot execute" when managed first-use remains.
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
  "context": {
    "productId": "my-product",
    "projectId": "cpr_...",
    "environment": "development"
  },
  "input": { "prompt": "cute slime icon", "model": "gpt-image-2.5-flare" },
  "execution": {
    "executionPreference": "automatic",
    "billingMode": "managed"
  }
}
```

If a workflow deliberately binds execution to a previously returned quote, the submitted job body must be unchanged and `execution.quoteId` may reference that quote. Execution remeasures pricing inputs against the sealed quote; a mismatch fails before work starts with `409 QUOTE_MISMATCH`. Never attach a stale quote ID just because a quote was requested earlier. `estimateId` is accepted as an inbound alias of `quoteId`.

## Pin an exact execution target

By default Hydracept chooses the provider and model for a capability and may re-seal to another eligible candidate. `pin` asks for one **exact** target and turns substitution off.

```json
{
  "context": { "productId": "my-product", "projectId": "cpr_..." },
  "input": {
    "messages": [{ "role": "user", "content": "Summarise this changelog." }]
  },
  "pin": { "target": "openai-text:gpt-5.6-terra" },
  "idempotencyKey": "<uuid-v4>"
}
```

`pin` is an object with one field, `target`. It is not part of `input` and not part of `execution`; sending it as an unknown extra field anywhere else is rejected with `422`. Where `pin` is supported, it is accepted on both synchronous invoke and durable job submission.

**Pin support is currently limited to `text.*` capabilities.** The durable job route rejects a `pin.target` on any other capability key with `422 PolicyRejected` and `details.reasons: ["target_pin_unsupported"]`, and domain capabilities reject it on invoke for the same reason. Neither `supportsExplicitTarget` nor a populated `targets` list overrides this: a compute capability can advertise targets and still refuse a pin. For a non-text capability, leave `pin` out and let Hydracept select.

`target` is a model reference: either `provider:model` or a bare model id when only one eligible provider ships that model. The provider id never contains `:` and a model id may, so Hydracept splits on the longest provider id it knows — `openai-compat-text:qwen3:14b` is one target, not a malformed one.

### Discover what you may pin

`GET /v1/capabilities/{key}/execution-targets` lists the models that can perform the capability. It is anonymous and it is the authoritative pinnable set — do not assume a model is pinnable because a provider advertises it.

```json
{
  "capability": "text.general.fast.v1",
  "defaultTarget": "openai-text:gpt-6.1-sol",
  "targets": [
    {
      "id": "openai-text:gpt-5.6-terra",
      "provider": "openai-text",
      "model": "gpt-5.6-terra",
      "apis": ["chat", "responses"],
      "kind": "text",
      "maturity": "production",
      "eligible": true,
      "availableNow": true,
      "availabilityReason": null,
      "readerDelivery": true
    }
  ]
}
```

- `id` is the value to send as `pin.target`. It is `provider:model`.
- `eligible` means the target can perform this capability. **Eligibility is not availability**: `availableNow: false` with `availabilityReason: "provider_unavailable"` means the target is otherwise valid but the provider is down right now. A pin does not wait for or route around that.
- `defaultTarget` is the unpinned selection, not a recommendation.
- `readerDelivery` is a per-target fact. Pinning a target that does not support it does not move the job onto one that does.

Some capabilities deliberately expose a single sealed target — classifiers and sealed decision routes select their own model, so their `targets` list holds exactly one entry and catalog siblings stay undiscoverable as pins. A capability can also expose no pinnable target at all, in which case `supportsExplicitTarget` is `false` on the descriptor (compute and CPU-processing capabilities do), and a pin is refused.

`execution-targets` describes eligibility; it does not by itself promise that a given route accepts a `pin` today. See the text-only limitation above and treat the pin error table below as the authority on what a specific capability will do.

### What "no substitution" means

A `pin` is a hard pin, not a preference:

- Hydracept dispatches only to the pinned provider and model. There is no re-seal to an alternate candidate, no second attempt on another route, and no silent model swap.
- One `pin` authorizes at most one provider attempt. The sealed routing authority records `fallbackPolicy: "none"` and `maximumAttempts: 1`.
- If the pinned target turns out to be unknown, ineligible, or momentarily unavailable, the request **fails**. Hydracept does not deliver a different model's output and call it a success.
- `pin` is not an additive control layered on another selector. Combining it with `modelSelection` rejects the request (`conflicting_model_selectors`); combining it with a `preferredModel` naming a *different* target rejects it as `conflicting_target_pin`. Naming the same target in both is accepted, but redundant.

Use `modelSelection` (`mode: "exact"` for one model, or `ordered` / `prefer` for authorized fallbacks) when you want ordered fallback rather than an exact target. Use no selector at all when you want Hydracept to choose.

### What the response reports back

Both the invocation result and the receipt disclose which target actually ran, so you never have to infer it:

| Field | Where | Meaning |
|-------|-------|---------|
| `resolvedProvider` / `resolvedModel` | invoke result, job | The sealed candidate that executed |
| `servedCandidateId` | invoke result | `provider:model:capabilityKey` of the client that was actually called |
| `selectedCandidateId` | invoke result | The candidate id chosen at admission |
| `route.routingPolicy` | receipt | `target_exact` when a `pin` sealed the route |
| `targetRouting.requestedTarget` / `resolvedTarget` | receipt | What you asked for, and what ran |
| `targetRouting.substituted` | receipt | `false` on a pinned execution; a pinned run is never substituted |

Read `servedCandidateId` when you need the identity of the execution for your own records. It normally equals `resolvedProvider:resolvedModel:capabilityKey`; a different value is itself evidence that the provider served something other than the sealed candidate, and Hydracept reports it rather than hiding it.

### What the errors mean

A pin that cannot be honored fails closed. The HTTP status separates an unusable request from an admission policy rejection.

| Response | `code` | `details.reasons` | Meaning |
|----------|--------|-------------------|---------|
| `422` | `PolicyRejected` | `target_pin_unsupported` | This capability or route does not accept `pin.target` |
| `422` | `InvalidInput` / `UNKNOWN_EXECUTION_FIELD` | — | `pin` placed at the wrong level, or an unknown key inside it |
| `403` | `PolicyRejected` | `target_unknown` | `pin.target` is not a known execution target |
| `403` | `PolicyRejected` | `target_ineligible` | The target exists in the catalog but cannot perform this capability |
| `403` | `PolicyRejected` | `target_unavailable` | The target is eligible but its provider is temporarily unavailable |
| `403` | `PolicyRejected` | `conflicting_target_pin` | `pin.target` and `preferredModel` name different targets |
| `403` | `PolicyRejected` | `conflicting_model_selectors` | `pin.target` was combined with `modelSelection` |

None of these are retryable with the same body except `target_unavailable`, which clears when the provider returns. For the others, either choose an `id` from `/execution-targets` or drop the pin. A retry is a new request: use a new `idempotencyKey`.

Admission policy rejections are recorded on the execution and return a `receiptId`, so a refused pin is still auditable.

### Quotes and pinned execution

`POST /v1/capabilities/{key}/quote` and `/estimate` do **not** accept `pin` — it is an unknown field there and is rejected with `422`. A pinned invoke prices its own pinned target on the way to admission and seals that price onto the execution; you do not pass a separate quote body for it.

When you want an explicit preview of a specific model, name it in the quote body as `input.model`. That is the pricing selector, and it resolves against the same catalog identity space the execution targets use:

```json
{
  "context": { "productId": "my-product", "projectId": "cpr_..." },
  "input": {
    "messages": [{ "role": "user", "content": "Summarise this changelog." }],
    "model": "gpt-5.6-terra"
  }
}
```

A quote is a preview and reserves nothing. For a pinned execution, do not attach the returned `quoteId` unless the submitted body is unchanged — otherwise the request fails with `409 QUOTE_MISMATCH` before work starts. The route that actually ran is the one on the receipt, not the one you previewed.

## Invoke vs durable jobs

| Route | Use when |
|-------|----------|
| `POST /v1/capabilities/{key}/invoke` | Short synchronous work that fits in one request |
| `POST /v1/capabilities/{key}/jobs` | Work that needs retries, polling, artifacts, or receipts |

Use jobs for image, audio, 3D mesh, and any generation that may take longer than one HTTP request.

`text.general.fast.v1` still offers `invoke_sync`. That call is held until the provider read timeout (600s). There is no separate token ceiling. Sync and durable jobs both derive the output cap from the model, the context window, and the response schema; `maxOutputTokens` is an optional hint. Eligible durable jobs use deferred processing and may wait 900s. The activity deadline is the shared durable ceiling (default and max 7200s), which stays above that provider wait. Queue timeout, execution timeout, and post-submit ambiguity are different error codes (`QueueTimeout`, `ExecutionTimeout`, `TRANSPORT_AMBIGUOUS`).

Durable text jobs (`executionModes` includes `job_async`) on eligible models also use **deferred processing**: Hydracept waits for the cheaper latency-tolerant provider tier and charges **50% of standard token rates**. Check `features.deferredProcessing` on the capability descriptor, or read [Deferred processing](../deferred-processing/). Synchronous invoke and stream stay on standard processing.

Audio capabilities (`audio.sfx.generate.v1`, `audio.voice.generate.v1`, `audio.music.generate.v1`) run as durable jobs. Output defaults to **Ogg** (`audio/ogg`) with a `.ogg` filename. Set `outputFormatPreference` to request another format — for example `mp3_44100_128` returns `audio/mpeg` with a `.mp3` filename. Supported values are `mp3_22050_32`, `mp3_24000_48`, `mp3_44100_32`, `mp3_44100_64`, `mp3_44100_96`, `mp3_44100_128`, `mp3_44100_192`, `opus_48000_32`, `opus_48000_64`, `opus_48000_96`, `opus_48000_128`, and `opus_48000_192`. The artifact `mediaType` and filename always match the format returned. Set `variantCount` (1–4) in job input to request multiple takes. See [variant selection](../jobs/#select-a-variant) when you need to pick one output before the next pipeline step.

For `audio.voice.generate.v1`, omit `voiceId` to use the managed default voice. Quotes, job snapshots, and receipts include the effective `voiceId`. Voice choice does not change the metered hold.

List other selectable voices with `GET /v1/capabilities/audio.voice.generate.v1/voices`. The response includes `voiceId`, `name`, and optional category, description, and preview URL. It uses the project's bound provider credential when configured, otherwise the managed platform key, and reports which source supplied the list.

Audio model ids are enumerable from each capability: `GET /v1/capabilities/{capabilityKey}` returns
`inputSchema.properties.modelId.enum`. Use one of those ids as `modelId`; a provider model name that is not in
the list is not executable. The canonical values are `eleven_text_to_sound_v2` for SFX; `eleven_v4` (default),
`eleven_multilingual_v2`, `eleven_turbo_v2_5`, and `eleven_flash_v2_5` for voice; and `music_v2` (default) and
`music_v1` for music.

`image.generate.v1` width and height snap up to multiples of 16 (Open Graph 1200×630 becomes 1200×640).

3D capabilities (`model.generate.3d.v1`, `model.generate.3d.from-image.v1`) run on Meshy. Use `model.generate.3d.v1` when you have turnaround view artifacts; use `model.generate.3d.from-image.v1` to chain OpenAI turnaround generation from a single concept image. See [5-minute 3D asset](../five-minute-3d-asset/).

`decision.evaluate.v1` evaluates structured state against typed questions. Send `state` (text, object, or array) and `questions`. Each question is `boolean`, `choice`, or `score`. Do not send `model` or chat `messages`; the sealed route selects the model. Output tokens are reported and priced at zero. Sync invoke and durable jobs are both available.

## Available capabilities

Discover the live catalog with `GET /v1/capabilities` or `python -m hydracept agent-context`. The live catalog is the source of truth, not a frozen list in this page.

Use the published capability keys from that catalog in your integrations.

## Missing capability?

If the catalog does not cover the outcome you need, call `POST /v1/capabilities/resolve` first. A `no_match_requestable` result may be filed as a non-binding **capability request**; a human can then quote and commission the implementation. Agents can read the quote but never pay it. See [Capability requests](../capability-requests/).

## Example: discover image generation

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/capabilities/image.generate.v1
```

See [Durable Jobs & Receipts](../jobs/) and [Quick Start](../).

## Moderation and classification

`text.moderate.v1` classifies text and returns category evidence your product owns the policy for. It runs as synchronous invoke only, takes `{"text": ...}` up to 20,000 characters, and is free at the managed retail price. `moderation.content.v1` is the deprecated provider-aligned name for the same classifier.

See [Moderation & classification](../moderation/).

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
