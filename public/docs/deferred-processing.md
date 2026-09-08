# Deferred processing

Hydracept **deferred processing** uses OpenAI Flex (`service_tier=flex`) at **50% of standard token rates**.

It applies to:

- Eligible durable text jobs (`POST /v1/capabilities/{key}/jobs`) — **default**
- Eligible OpenAI Responses pins (`POST /v1/inference/pinned` and bulk items) — **opt in** with `processing: "deferred"`

Interactive invoke and stream stay on standard processing. Image, audio, video, and 3D jobs are unchanged — those providers do not expose this discount today.

## When it applies

| Path | Processing |
|------|------------|
| `POST /v1/capabilities/{key}/jobs` (`job_async`) | Deferred when the routed model supports it. HTTP 429 retries stay on Flex; a Flex `400` retries once on standard rates. |
| `POST /v1/inference/pinned` and `/pinned/bulk` | **Standard by default.** Opt in with `processing: "deferred"` on eligible OpenAI Responses pins. Same pin, one logical model execution, no truncation rewrite, no Flex→Standard fallback. Flex-capacity 429s retry inside the admission deadline and are recorded on the receipt. Omitted execution timeouts on Flex pins use the 600s platform max. |
| `POST /v1/capabilities/{key}/invoke` | Standard |
| Stream | Standard |

Discover support on the capability descriptor:

```http
GET /v1/capabilities/text.reasoning.high.v1
```

Look for:

```json
"features": {
  "deferredProcessing": {
    "available": true,
    "discountBps": 5000,
    "appliesTo": ["job_async", "pinned"],
    "defaultFor": ["job_async"],
    "optInFor": ["pinned"]
  }
}
```

Receipts record `processingTier` and `deferredDiscountBps` on every pin. The discounted upstream basis is recorded only when deferred actually ran.

Pinned native envelopes add `service_tier: "flex"` only when the caller opts in (plus the existing `store: false`). Hydracept does not send Responses `truncation` and does not change `max_output_tokens`.

## BYOK and managed

The 50% applies to the **provider token basis**, not the Hydracept service fee.

- **BYOK** — you pay the provider 50% of standard token rates for eligible deferred calls. Hydracept fee remains 0%.
- **Managed** — the published upstream basis is the discounted rate, then the catalog Hydracept service fee applies. Managed pinned remains unavailable (`501`).

See [Billing](../billing/), [Durable jobs](../jobs/), and [Pinned Execution](../pinned-execution/).
