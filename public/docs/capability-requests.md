# Capability requests (commissioned capabilities)

Hydracept ships a fixed catalog of capability keys. When an agent needs an outcome that is not in the live catalog, it can file a **capability request** describing the missing work. A human operator reviews the request and, if it is in scope, issues a **commission quote**. Only a human can accept and pay that quote.

Commission quotes are the opposite of execution quotes: they fund **implementation of a capability that does not exist yet**, they are non-binding until paid, and their `quoteId` must never be attached to a job as `execution.quoteId`.

## Flow

1. **Resolve first.** `POST /v1/capabilities/resolve` with the intended outcome. Missing capabilities are a normal result.
   - `resolution: "supported"` — use the matched capability; no request needed.
   - `resolution: "no_match_requestable"` — a request may be filed. `nextAction` names `POST /v1/capability-requests`.
   - `resolution: "no_match_not_requestable"` — out of the supported product boundary; do not file.
2. **Create a request.** `POST /v1/capability-requests` returns a `draft` with a stable `id`.
3. **Revise (optional) and submit.** `POST /v1/capability-requests/{id}/revisions` freezes a new revision hash; `POST /v1/capability-requests/{id}/submit` sends the current revision for human review.
4. **An operator issues a quote.** Internal review produces a commission quote with a price in your account billing currency (USD or CAD). A request can also be declined or returned as `needs_information`.
5. **Read the quote (non-binding).** `GET /v1/capability-requests/{id}/quote` returns the `CapabilityQuoteView`.
6. **A human pays.** The quote carries `approval.approvalUrl`; only an authenticated member of the owning organization (or a platform operator) can start checkout. Paying starts implementation.
7. **Fulfilment.** The operator records the shipped capability key; the request reaches `fulfilled`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/capabilities/resolve` | Decide whether a suitable capability already exists |
| `POST` | `/v1/capability-requests` | Create a request (`hydracept.capability-request.v1`) |
| `GET` | `/v1/capability-requests/{id}` | Read a request, its revision, and any customer feedback |
| `POST` | `/v1/capability-requests/{id}/revisions` | Add a revision (invalidates an active quote) |
| `POST` | `/v1/capability-requests/{id}/submit` | Submit the current revision for review |
| `GET` | `/v1/capability-requests/{id}/quote` | Read the commission quote (human-paid) |

Operator-only surfaces are not part of the public contract.

## Create a request

```http
POST /v1/capability-requests
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

```json
{
  "schemaVersion": "hydracept.capability-request.v1",
  "summary": "Vectorize a raster logo into clean SVG paths",
  "need": "Our pipeline produces PNG logos but the destination store needs layered SVG.",
  "proposedCapability": { "capabilityKey": "image.vectorize.v1" },
  "acceptanceCases": [
    { "input": "512x512 PNG logo", "expected": "SVG with fewer than 40 paths" }
  ],
  "constraints": { "maxLatencySeconds": 120 }
}
```

`summary` and `need` are required. `projectId`, `proposedCapability`, `constraints`, `acceptanceCases`, and `implementationPreferences` are optional and are frozen into the revision hash shown to the human.

## Read the commission quote

```http
GET /v1/capability-requests/cr_.../quote
Authorization: Bearer <HYDRACEPT_API_KEY>
```

```json
{
  "quoteId": "cq_...",
  "quoteKind": "commission",
  "notExecutionQuoteId": true,
  "requestId": "cr_...",
  "requestRevisionId": "crr_...",
  "requestHash": "sha256:...",
  "commissionPrice": { "amountMicros": 250000000, "currency": "USD", "display": "US$250.00" },
  "taxTreatment": "tax_calculated_at_checkout",
  "runtimePricing": { "mode": "metered", "status": "projected", "billingCurrency": "USD" },
  "delivery": { "targetBusinessDays": 10 },
  "guarantee": { "kind": "full-satisfaction-refund", "acceptanceWindowDays": 7 },
  "expiresAt": "2026-10-01T00:00:00Z",
  "approval": { "humanRequired": true, "approvalUrl": "https://app.hydracept.com/approve/capability-quotes/cq_..." }
}
```

- **`quoteKind: commission`** — implementation pricing, not execution pricing.
- **`notExecutionQuoteId: true`** — this id is never valid as `execution.quoteId`.
- **`commissionPrice`** — implementation fee before tax; `amountMicros` is authoritative.
- **`runtimePricing.status`** — `projected` until the capability ships. A commission cannot promise exact runtime pricing for software that does not exist yet.
- **`expiresAt`** — quotes expire after 14 days. Reading an expired quote returns `410`.

## Pay (humans only)

Open `approval.approvalUrl` in a browser. After signing in, a member of the owning organization sees a Stripe checkout for `commissionPrice`. Agents must stop and present the URL; they must never pay or accept a commission quote. `GET /quote` does not reserve funds and spends nothing.

## CLI

```bash
python -m hydracept capability-request create request.json
python -m hydracept capability-request show cr_...
python -m hydracept capability-request submit cr_...
python -m hydracept capability-request quote cr_...
```

## MCP

- `request_capability_quote` — create and submit a request (non-binding).
- `get_capability_request_quote` — read the commission quote.

## Semantics and guarantees

- **Non-binding** — filing a request and reading a quote cost nothing.
- **Human-authorized** — no agent can accept or pay a commission quote.
- **Frozen scope** — the quote is bound to the request revision hash; adding a revision invalidates an active quote.
- **Refund guarantee** — `full-satisfaction-refund` with a 7-day acceptance window. An operator can request a refund on a paid commission.
- **Expiry** — an expired quote cannot be accepted, even if checkout is retried.
