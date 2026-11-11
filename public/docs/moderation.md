# Moderation and text classification

`text.moderate.v1` classifies text for policy risk. It returns **evidence**, not a verdict: Hydracept selects the classifier, records the execution, and hands you provider category flags and scores. Your product decides whether a flag blocks, warns, or is allowed.

`moderation.content.v1` is the same classifier behind a deprecated provider-aligned name. New integrations should use `text.moderate.v1`.

## Request shape

`text.moderate.v1` takes one string. That is the whole input — there is no `messages` array, no system prompt, and no per-request model choice.

```http
POST /v1/capabilities/text.moderate.v1/invoke
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

```json
{
  "context": { "productId": "my-product", "projectId": "cpr_..." },
  "input": { "text": "The text you want classified." },
  "idempotencyKey": "<uuid-v4>"
}
```

`input` is `{"text": string}` and nothing else. `text` is required, must be non-empty, and is capped at **20,000 characters**; the limit is published on the descriptor as `inputConstraints.text` with `overflow: "reject"`. Hydracept does not truncate — an over-length body fails with `422 PromptTooLong` before any provider call. Unknown keys inside `input` are rejected.

`text.moderate.v1` runs as synchronous invoke only. `GET /v1/capabilities/text.moderate.v1` reports `executionModes: ["invoke_sync"]`; there is no durable job variant, so you do not need polling, artifacts, or a receipt round-trip to classify text.

There is no separate `minimalInput` shortcut to learn: `features.minimalInput` on the descriptor is `{"text": "..."}`, the same shape.

## Output shape

```json
{
  "schemaVersion": "text.moderate.v1",
  "flagged": true,
  "categories": {
    "violence": { "flagged": true, "score": 0.91 },
    "sexual": { "flagged": false, "score": 0.08 }
  },
  "provider": "openai-moderation",
  "model": "omni-moderation-latest",
  "availability": "Available"
}
```

- `flagged` — the provider's overall verdict. It may be `null`, which means **no classification was produced**. `null` is never an implicit approval; treat it as unknown and fail closed.
- `categories` — a map of provider category name to `{flagged, score}`, where `score` is `0.0`–`1.0`.
- `availability` — `Available`, `TimedOut`, or `ProviderError`. When it is not `Available`, `flagged` is `null`, `categories` is `{}`, and `error` carries a short reason.
- `provider` / `model` — which classifier produced the evidence.

The result arrives as `typedOutput` on the invocation result.

## Category names

**Hydracept does not publish a fixed category list.** Category names are provider-derived and are passed through unchanged — Hydracept does not rename, drop, merge, or reinterpret them, and it does not normalize them across providers. The descriptor advertises this as `features.providerReportedCategoryNames: true`.

Read the keys of `categories` at runtime rather than coding against a remembered set. A category you have never seen is normal, not an error, and a category you expected may be absent when the provider did not evaluate it. This is why a product policy should be written against the categories it actually needs to act on, with an explicit default for everything else.

## `classificationOnly`

`features.classificationOnly: true` states the contract's scope: this capability answers "what does the classifier observe about this text" and does nothing else.

- It does not block, redact, sanitize, quarantine, or rewrite the text.
- It does not gate your model calls. A `flagged: true` classification is not a Hydracept refusal, and Hydracept will happily classify the same text again.
- It does not moderate anything Hydracept generates for you. Output moderation is a call you make, in your own order, on text you choose.
- It is not a content-policy engine: `features.productPolicyEngine` is `false`.

One classification is one data point about one string. Deciding what that means for a turn, a user, or an account is your application's job.

## Who owns policy

**You do.** `features.productPolicyOwnedByCaller: true`.

Hydracept owns the classifier selection, the execution record, and the shape of the evidence. Your product owns the thresholds, the escalation rules, the age-appropriateness judgement, and the user-facing outcome. Two products can receive identical evidence and correctly behave differently — a horror game and a children's app should map the same `violence` score to different actions.

Practical consequences:

- Do not treat a single `flagged` boolean as proof a piece of content is or is not appropriate. Use the scores and your own context.
- Build the unavailable path first. `availability: "TimedOut"` or `"ProviderError"` must produce a safe fallback in your product, not an unmoderated response. A provider failure is never an approval.
- Re-classify text you generated before you show or speak it, if your policy requires it. Hydracept will not do that for you.

## Cost

`text.moderate.v1` is **free** at the retail price.

- Managed: `billingModes.managed.pricing` reports `mode: "fixed"` with the display text *"Free. The managed OpenAI omni-moderation classifier is included at a zero retail price with no per-call minimum."* The managed classifier is included; you do not need a provider account.
- BYOK: `billingModes.byok` is available and carries a 0% Hydracept fee, but the provider charges your connected account separately.
- `pricingFactors` is empty and `estimateRequired` is `false`. Quoting a zero-priced capability is allowed but tells you nothing you did not already know.
- Per-token accounting still appears in `usage`; it is priced at zero.

`moderation.content.v1` is priced differently: its managed display reads *"Billed at actual managed provider cost per request with no per-call minimum."* The classifier is currently free upstream, so the charge is zero in practice, but the pricing mode is actual-cost rather than a declared fixed zero. If cost certainty matters, use `text.moderate.v1`.

Both keys run on the managed classifier Hydracept selects. **You cannot pin your way to another moderation model**: the capability exposes exactly one execution target, and a `pin` naming any other model fails with `target_ineligible`. See [Capabilities](../capabilities/#pin-an-exact-execution-target).

## Example

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "context": { "productId": "my-product", "projectId": "cpr_..." },
    "input": { "text": "A polite chapter opening." },
    "idempotencyKey": "moderate-001"
  }' \
  https://api.hydracept.com/v1/capabilities/text.moderate.v1/invoke
```

Fail closed on the result:

```python
result = response.json()
output = result["typedOutput"]
if output.get("availability") != "Available":
    return safe_fallback()          # never treat a failure as approval
if output["flagged"] is None:
    return safe_fallback()          # no classification produced
if output["flagged"] or output["categories"].get("violence", {}).get("score", 0) > 0.8:
    return block_or_review()
```

## The legacy key

`moderation.content.v1` still works and stays in anonymous discovery so existing callers keep running. Differences to know before you migrate or depend on it:

| | `text.moderate.v1` | `moderation.content.v1` |
|---|---|---|
| Status | canonical | deprecated (`features.deprecated: true`) |
| Input | `{"text": string}` | `{"messages": [...]}` or `{"content": string}` |
| Execution | `invoke_sync` | `invoke_sync`, `job_async` |
| Output | `flagged`, `categories` map | `providerFlagged`, `overallRiskScore`, `categories` array, `flags` array |
| Pricing mode | fixed (free) | actual managed provider cost |

`features.replacement` on the legacy descriptor names `text.moderate.v1`. The legacy output shape is frozen and will not gain features.

## Related

- [Capabilities](../capabilities/) — discovery, quotes, and pinning
- [Errors](../errors/) — `PolicyRejected`, `PromptTooLong`, and retry semantics
- [Billing & plans](../billing/) — managed fees and the zero-price case
- [Classification and data handling](../data-handling/) — what a declared `dataClassification` commits you to
