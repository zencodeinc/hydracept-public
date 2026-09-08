# Rate limits & quotas

Every request is checked against your plan limits and the budget you configure.

## What is limited

Plans are **Free / Builder / Team / Enterprise**. Limits are YAML-tunable in the launch catalog:

- short requests (in progress, per hour, and per month) — includes pinned execution
- active generation jobs
- local / accelerated transforms
- streaming connections
- retained payload bytes and history retention days
- project, environment, seat, and API-key limits

Enterprise customers can discuss additional capacity with support. See [Hydracept pricing](https://hydracept.com/pricing).

## Signals

When you hit a limit, the API returns:

- `429` for rate limiting
- `402` for budget exceeded (including BYOK provider-spend guardrails)
- `403` when your plan or project configuration does not allow the request

Retry with backoff on `429`. For `402`, review project budgets, wallet, or your own guardrail at [Studio Billing](https://app.hydracept.com/studio/billing) — see [Billing & plans](../billing/). For `403`, review plan entitlements or contact support for Enterprise.

## Budgets

Execution options can carry budget constraints. BYOK still bills your provider account; Hydracept guardrails help prevent runaway spend before work starts. These guardrails are not an additional Hydracept charge.

## Related

- [Billing & plans](../billing/)
- [Errors](../errors/)
- [Authentication & Activation](../authentication/)
