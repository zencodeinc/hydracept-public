# Errors

Failed control-plane calls return an HTTP status code and a stable public error envelope.

## Typical statuses

| Status | Meaning |
|--------|---------|
| `400` | Invalid request / policy rejection |
| `401` | Missing or invalid Hydracept API key / session |
| `402` | Budget exceeded |
| `403` | Not allowed for this principal / project / environment |
| `404` | Capability, job, or resource not found |
| `409` | Conflict (including idempotency conflicts) |
| `422` | Request validation failed |
| `429` | Rate limited |
| `503` | Provider unavailable |

## Envelope

Error bodies usually include:

- `code` — stable Hydracept error code
- `message` — human-readable explanation
- optional detail fields for validation failures

Parse Hydracept `code` values from the public OpenAPI and runtime responses—not provider-native error strings.

## Idempotency

Durable job submits accept `idempotencyKey`. Replaying the same key with a conflicting payload returns `409` instead of creating a second job.

## Related

- [Rate limits & quotas](../rate-limits/)
- [Durable Jobs & Receipts](../jobs/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
