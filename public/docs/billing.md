# Billing & plans

Hydracept has four public plans: **Free**, **Builder**, **Team**, and **Enterprise**. Plans control capacity, retention, seats, and shared-workspace features — not routing quality, pin semantics, or receipt evidence.

See live prices on [hydracept.com/pricing](https://hydracept.com/pricing).

> Bring your own provider at 0%. Use Hydracept-managed providers at provider price + 6%. Upgrade your plan when you need more Hydracept capacity or organizational features.

## BYOK (bring your own key)

Connect your own provider credentials and pay your provider directly. Hydracept adds **0% inference markup**. Provider-spend guardrails help you set a daily safety budget and are not an additional Hydracept charge.

Durable text jobs use **deferred processing** automatically: Hydracept submits them on the provider's latency-tolerant tier at **50% off** standard token rates. Eligible OpenAI Responses pins stay on standard processing unless you set `processing: "deferred"`. Interactive invoke and stream stay on standard processing. See [`features.deferredProcessing`](../deferred-processing/) on capability descriptors.

## Managed inference (PAYG)

Hydracept can run generation on platform credentials using a **prepaid wallet**:

- **No subscription required** for managed inference
- Transparent pricing: published upstream basis + **6% Hydracept service fee**
- One managed fee across all capabilities (text, images, video, 3D, workflows)
- New ordinary Free accounts receive a one-time **US$0.50 managed trial allowance** for setup/smoke verification
- **Wallet top-up is live** (`walletTopUpLive: true` in the well-known manifest). Add funds from Studio Billing or `POST /v1/billing/wallet/top-up-session`.

Example:

```text
Provider basis              $1.00
Hydracept service fee (6%)  $0.06
──────────────────────────────────
Your total                  $1.06
```

Check capability discovery for managed availability:

- `GET /v1/capabilities` — inference capabilities include `billingModes.byok` and `billingModes.managed`; domain and CPU processing omit `billingModes`
- `POST /v1/capabilities/{key}/quote` — firm retail price before you run a job (does not reserve funds). `POST .../estimate` is a 0.2 serialization shim.

Receipts keep the fee snapshot they were created under. Historical charges are never recomputed when the catalog fee changes.

## Free ($0)

Genuinely useful for evaluation, hobby projects, and occasional generation.

- 1 user · 3 projects
- 2 concurrent durable jobs · 10 active durable jobs
- 1,000 lightweight inferences / hour
- 30-day history
- BYOK and managed execution
- All generally available capability types

Two concurrent durable jobs is the conversion pressure — not capability gating.

## Builder ($19 / month)

For a serious individual developer who has outgrown Free.

- 1 user · 10 projects
- 10 concurrent durable jobs · 40 active durable jobs
- 4,000 lightweight inferences / hour
- 90-day history
- Personal provider vault, receipts, artifacts, and normal routing

Primary upgrade trigger: *two concurrent jobs is slowing me down.*

## Team ($149 / month)

Organizational production, not the first paid tier.

- 5 included users · 25 projects
- 30 concurrent durable jobs · 150 active durable jobs
- 25,000 lightweight inferences / hour
- 180-day history
- Shared provider vault, organization budgets, roles, and production controls

Inference can still run on BYOK at 0% Hydracept fee. Managed execution remains PAYG + 6%.

## Enterprise

Sales-only. Larger teams, volume commitments, SLA, SSO, private networking, custom retention, and contractual terms. Request Enterprise at support@hydracept.com — there is no self-serve checkout.

## How to upgrade (Studio)

1. Sign in at [app.hydracept.com/login](https://app.hydracept.com/login)
2. Open **Billing** in Studio: [app.hydracept.com/studio/billing](https://app.hydracept.com/studio/billing)
3. Choose **Builder** ($19) or **Team** ($149) — checkout is hosted by Stripe
4. An upgrade immediately refreshes admission capacity. You do not recreate the account.
5. Use **Manage billing** for invoices, payment method, or cancellation
6. Add wallet funds from the same page or `POST /v1/billing/wallet/top-up-session`
7. Set **provider safety budgets** on the same page (not a Hydracept charge)

## API

- `GET /v1/billing/summary` — plan, subscription, and managed inference wallet summary
- `GET /v1/billing/wallet` — wallet balances (available, reserved)
- `GET /v1/billing/wallet/transactions` — immutable wallet transaction log
- `POST /v1/billing/wallet/top-up-session` — prepaid wallet top-up (`walletTopUpLive: true`)
- `GET /v1/billing/guardrails` — BYOK provider-spend guardrails
- `PATCH /v1/billing/guardrails` — update daily / per-execution safety budgets
- `GET /v1/billing/plans` — purchasable plans (Builder, Team)
- `POST /v1/billing/checkout-session` — subscription checkout
- `POST /v1/billing/portal-session` — Stripe Customer Portal
- `GET /v1/capabilities` — inference capabilities include `billingModes`; domain and CPU processing omit them

## When you hit limits

Capacity limits are machine-readable. A durable concurrency error looks like:

```json
{
  "code": "DURABLE_CONCURRENCY_LIMIT",
  "message": "This project currently has 2 durable jobs running and the free plan allows 2.",
  "details": {
    "current": 2,
    "plan": "free",
    "upgrade": {
      "plan": "builder",
      "displayName": "Builder",
      "monthlyUsd": 19,
      "concurrentDurableJobs": 10
    }
  }
}
```

- `402` / budget errors — review project budgets, wallet balance, BYOK guardrails, and plan capacity
- `403` — plan entitlement blocked the action; the `details` object names the limit and the next plan
- `429` — rate limit; retry with backoff

See [Rate limits & quotas](../rate-limits/).

## Related

- [Authentication & Activation](../authentication/)
- [Connections / BYOK](../connections/)
- [Deferred processing](../deferred-processing/)
- [Pinned Execution](../pinned-execution/)
- [Execution provenance](../provenance/)
- [Terms](https://hydracept.com/terms.html)
