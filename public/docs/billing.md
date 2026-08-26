# Billing & plans

Hydracept has three public plans: **Free**, **Team**, and **Enterprise**. Plans determine how much your team can run, how long history is retained, and which workspace features are available.

See live prices on [hydracept.com/pricing](https://hydracept.com/pricing).

## BYOK (bring your own key)

Connect your own provider credentials and pay your provider directly. Hydracept adds **0% inference markup**. Provider-spend guardrails help you set a daily safety budget and are not an additional Hydracept charge.

## Managed inference (PAYG)

Hydracept can run generation on platform credentials using a **prepaid wallet**:

- **No subscription required** for managed inference
- Transparent pricing: published upstream basis + **10% Hydracept service fee**
- Free includes a one-time trial wallet for setup verification (see the live catalog)
- **Wallet top-up is not live** (`walletTopUpLive: false` in the well-known manifest). Use the trial or connect BYOK.

Example at launch:

```text
Provider basis (Recraft V4)     $0.040
Hydracept service fee (10%)     $0.004
──────────────────────────────────────
Your total                      $0.044
```

Check capability discovery for managed availability:

- `GET /v1/capabilities` — each capability includes `billingModes.byok` and `billingModes.managed`
- `POST /v1/capabilities/{key}/quote` — firm retail price before you run a job (does not reserve funds). `POST .../estimate` is a 0.2 serialization shim.

## Free

- $0 for individual developers
- 1 environment · 3 projects
- 1,000 lightweight inferences / hour · 2 concurrent durable jobs · 10 active durable jobs
- 30-day history
- Optional trial wallet credit for first-run verification
- Connect provider keys on [Connections / BYOK](../connections/) for sustained BYOK generation

## Team ($49 / workspace)

Paid Team raises capacity, retention, seats, and shared-workspace features:

- 5 environments · 20 projects · 5 seats
- 10,000 lightweight inferences / hour · 10 concurrent durable jobs · 60 active durable jobs
- 180-day history
- Shared vault and org budget policies

Inference can still run on BYOK at 0% Hydracept fee. There is no monthly wallet grant — managed inference is PAYG. Live numbers: [hydracept.com/pricing](https://hydracept.com/pricing).

## Enterprise

Sales-only. Negotiated scale, retention, and support. Contact sales — do not self-serve checkout.

## How to upgrade (Studio)

1. Sign in at [app.hydracept.com/login](https://app.hydracept.com/login)
2. Open **Billing** in Studio: [app.hydracept.com/studio/billing](https://app.hydracept.com/studio/billing)
3. Choose **Upgrade to Team** — checkout is hosted by Stripe when enabled
4. Use **Manage billing** for invoices, payment method, or cancellation
5. Wallet top-up is **not live** yet — use the Free-plan trial or [BYOK](../connections/)
6. Set **provider safety budgets** on the same page (not a Hydracept charge)

## API

- `GET /v1/billing/summary` — plan, subscription, and managed inference wallet summary
- `GET /v1/billing/wallet` — wallet balances (available, reserved)
- `GET /v1/billing/wallet/transactions` — immutable wallet transaction log
- `POST /v1/billing/wallet/top-up-session` — not live (`walletTopUpLive: false`)
- `GET /v1/billing/guardrails` — BYOK provider-spend guardrails
- `PATCH /v1/billing/guardrails` — update daily / per-execution safety budgets
- `GET /v1/billing/plans` — purchasable plans (Team)
- `POST /v1/billing/checkout-session` — subscription checkout
- `POST /v1/billing/portal-session` — Stripe Customer Portal
- `GET /v1/capabilities` — includes `billingModes` per capability

## When you hit limits

- `402` / budget errors — review project budgets, wallet balance, BYOK guardrails, and plan capacity
- `403` — plan entitlement blocked the capability; upgrade or contact support for Enterprise
- `429` — rate limit; retry with backoff

See [Rate limits & quotas](../rate-limits/).

## Related

- [Authentication & Activation](../authentication/)
- [Connections / BYOK](../connections/)
- [Pinned Execution](../pinned-execution/)
- [Execution provenance](../provenance/)
- [Terms](https://hydracept.com/terms.html)
