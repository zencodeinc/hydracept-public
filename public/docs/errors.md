# Errors

Failed API calls return an HTTP status code. Structured capability errors return their Hydracept error information in a `detail` object; some standard HTTP errors use a string or validation details in `detail`.

## Typical statuses

| Status | Meaning |
|--------|---------|
| `400` | Invalid request / policy rejection |
| `401` | Missing or invalid Hydracept API key / session |
| `402` | Budget exceeded or managed wallet insufficient |
| `403` | Your API key, project, or environment is not allowed to make this request |
| `404` | Capability, job, or resource not found |
| `410` | Resource gone (expired session or retired endpoint) |
| `409` | Conflict (including idempotency conflicts) |
| `422` | Request validation failed |
| `429` | Rate limited |
| `503` | Provider unavailable |

## Structured capability errors

When an endpoint returns a structured capability error, its body has this shape:

```json
{
  "detail": {
    "code": "BudgetExceeded",
    "message": "The request exceeds the configured budget"
  }
}
```

`detail.code` is the stable Hydracept error code. `detail.message` is a human-readable explanation. Validation failures may use a different `detail` shape.

Handle the HTTP status first. When `detail.code` is present, use that Hydracept value rather than provider-native error strings.

Admission failures from invoke/jobs may return `{code, message, details}` at the top level (not wrapped in `detail`). MCP tools surface `code`, `connectUrl` / `upgradeUrl`, and `nextAction` when present.

| Code | What to do |
|------|------------|
| `USE_JOBS` | POST `/v1/capabilities/{key}/jobs` (`submit` in the error body) |
| `USE_INVOKE` | POST `/v1/capabilities/{key}/invoke` |
| `CONNECTION_REQUIRED` | Open `details.connectUrl` (or `connectUrl`) so a human connects BYOK |
| `EXTERNAL_ACTIONS_DISABLED` | Open `details.upgradeUrl` (Studio billing) |
| `QUOTE_MISMATCH` | Omit `execution.quoteId` and submit with a new `idempotencyKey` |
| `billing_managed_usage_exhausted` | Open `upgradeUrl` or connect BYOK |

### Managed inference

| Code | Meaning |
|------|---------|
| `billing_managed_usage_exhausted` | Wallet balance too low for the authorized estimate |
| `billing_not_configured` | Stripe / billing not enabled for this environment |

When `billingModes.managed.available` is `false` for a capability, use BYOK or choose another capability — do not rely on submit errors for discovery.

## Idempotency

Durable job submits accept `idempotencyKey` (minted if omitted). Replaying the same key with a conflicting payload returns `409` instead of creating a second job.

`409` with `detail.code` `QUOTE_MISMATCH` means a previously sealed `quoteId` no longer matches the job body. Omit `execution.quoteId` and submit with a **new** `idempotencyKey`.

## Related

- [Rate limits & quotas](../rate-limits/)
- [Durable Jobs & Receipts](../jobs/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
