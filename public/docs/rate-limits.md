# Rate limits & quotas

Every capability call is checked against your plan entitlements and runtime admission rules.

## What is limited

Depending on your plan (Free / Indie / Studio / Custom):

- concurrent jobs
- executions per hour
- active durable jobs
- retained payload bytes
- history retention days
- project / environment / service-principal counts

See pricing on [hydracept.com](https://hydracept.com/#pricing) for plan limits.

## Signals

When you hit a limit, the API returns:

- `429` for rate limiting
- `402` for budget exceeded
- `403` for other admission / entitlement denials

Retry with backoff on `429`. For `402`, raise budgets or upgrade your plan.

## Budgets

Execution options can carry budget constraints. BYOK still bills your provider account; Hydracept budgets gate admission and help prevent runaway spend in the control plane.

## Related

- [Errors](../errors/)
- [Authentication & Activation](../authentication/)
