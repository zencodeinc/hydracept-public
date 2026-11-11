# Classification and data handling

Every capability request can declare what kind of data it carries. That declaration is a **constraint you accept**, not a permission you are granted. This page covers what each classification commits you to, how Hydracept resolves the effective classification, and how to build a product that handles restricted data correctly.

## Declaring a classification

`context.dataClassification` on the invoke or job envelope takes one of six values:

| Value | Meaning |
|-------|---------|
| `Public` | Nothing sensitive. Safe to publish as-is. |
| `Internal` | Ordinary business content that should not be published. |
| `Confidential` | Contractually or commercially restricted content. |
| `PrivateUserContent` | Content belonging to an identifiable end user. |
| `Manuscript` | Long-form authored work under revision. |
| `ChildDirected` | Content from or about a child, under a parental or guardian consent record. |

The default is `Internal`. The enum is published on `CapabilityContext` in the public OpenAPI document.

```json
{
  "context": {
    "productId": "my-product",
    "projectId": "cpr_...",
    "dataClassification": "PrivateUserContent"
  },
  "input": { "messages": [{ "role": "user", "content": "..." }] },
  "idempotencyKey": "<uuid-v4>"
}
```

`context.retentionRequirement` is a second, independent declaration: `HashesOnly`, `Transient`, `EncryptedShortTerm`, `ProductManaged`, or `ProductionAsset`.

Together these two fields describe the handling you need. Neither one authorizes anything by itself.

## Two facts decide the effective classification

Hydracept computes the classification an execution must actually honor from two inputs, and **the stricter one always wins**:

1. **The project's server-side binding.** A project provisioned for restricted traffic stays restricted even when a caller declares something weaker. A request cannot lower this.
2. **The request's declaration.** A request can raise the floor but never lower it.

So there are three possible outcomes:

| Situation | Result |
|-----------|--------|
| Declaration is stricter than the project binding | The stricter declared class is honored |
| Declaration matches the binding | The binding is honored |
| Declaration is weaker than the binding | The request is rejected as a downgrade attempt |

A downgrade attempt returns `403` with `code: "classification_downgrade_rejected"`. This is a terminal caller bug, not a transient condition — never retry it with the same body, and never treat a re-declaration as a fix.

The practical rule: **declare the class your data actually is.** Declaring `Internal` for content that belongs to a user, or for content about a child, does not make the request more likely to succeed. It makes it more likely to be refused, and it is the single most common way integrations break at the classification boundary.

## Restricted classes and route approval

Each classification carries handling obligations that determine whether content may leave the platform at all:

- Content that requires a consent record, or that prohibits external processing, is refused unless an operator has approved the exact provider, model, region, and capability combination for that class.
- Approval is recorded per route, never as a wildcard over a whole provider catalog. An approved provider is not an approved model.
- **Absence of approval is denial.** There is no "unknown means allow" path. If no approval covers the route, the execution is refused.

When no route may carry the data, the API returns `403` with `code: "processing_not_permitted"` and `retryable: false`. When a profile covers the class but not this particular route, the code is `processing_route_unavailable` — a different signal, meaning the class is supported in principle but this provider/model is not approved for it.

Both checks run **before** credential resolution, input materialization, cost reservation, and provider dispatch. An ineligible route never produces a paid provider call.

## `ChildDirected` is refused by default

`ChildDirected` is the most restrictive class. It carries all of the following obligations at once:

- External processing is not permitted by default.
- Content is transient-only — it may not outlive the execution.
- The subject may not be identified across requests. No profile, no history, no cross-request correlation.
- Content must never be used to train, fine-tune, or evaluate a model.
- An externally issued, auditable consent record naming the consenting party is required. Hydracept may issue that record; it will never assume one exists.

Because of this, **`ChildDirected` requests are rejected with `403 processing_not_permitted` today, by design.** No managed route has an approved processing profile for child-directed traffic.

Consequences you should plan for:

- There is no configuration, header, or flag that makes real child traffic work right now. Build and test against synthetic, adult-authored fixtures only.
- **Do not relabel child content as `Internal` or `Public` to get it through.** A project bound to a restricted floor will reject the attempt as a downgrade, and a project that is not so bound will still be sending child data under a false declaration. Both outcomes are failures, and the second is a compliance incident that Hydracept cannot detect for you.
- Treat child-data admission as an independent, blocking dependency. It is not solved by picking a faster model, a cheaper route, or a different region.
- Check the project binding before you launch, not after. A restricted-floor project behaves differently for every capability, not just one.

If you need child-directed processing for a specific workflow, that is an operator decision backed by per-route contractual and technical evidence. It is not a client-side setting.

## Processing profiles

A processing profile is a versioned, operator-approved record that answers two questions for one classification:

1. Which `(provider, model, region, capability)` combinations may serve it.
2. How its payloads may be retained afterward.

Profile behavior you can rely on:

- **Deny by default at every branch.** No binding, no profile, a disabled profile, an unmatched route, an expired review date, or a missing region all deny.
- **Explicit model lists, not wildcards.** A profile may cover a version line with a trailing-`*` family pattern, but it never covers a provider's whole future catalog.
- **Approvals expire.** A route approval carries an `approvedAt` and a `reviewAt`; past the review date it stops authorizing anything.
- **Credential swaps invalidate approval.** An approval records the account configuration it assumes, so reusing it after swapping credentials is not automatic.
- **Fallback is constrained.** Under `approved_routes_only`, only routes listed on the same profile may be used. Under `none`, there is no failover at all. Fallback is never authorized by error rate or cost alone.
- **Retention is per payload class** — raw audio, transcripts, synthesized audio, and receipt content each carry their own mode: `transient`, `bounded`, `durable`, or `metadata_only`. `bounded` requires a TTL; a profile with no approval assumes the strictest possible retention.

Profiles apply where a capability opts in, and always where a project carries a floor. That keeps capabilities outside the registry on their existing behavior while restricting ones with stricter obligations.

## Retention declarations

`context.retentionRequirement` is checked against what your credential is permitted to request. A retention value your principal may not use is rejected with code `RetentionViolation` and `details.reasons: ["retention_not_allowed"]`.

Choose the weakest retention that meets your obligation, not the strongest you can get away with:

- `HashesOnly` — you need to prove an execution happened, not what it contained.
- `Transient` — you need the output now and nothing later. The default.
- `EncryptedShortTerm` — you need to read it back within a bounded window.
- `ProductManaged` — you retain it in your own store and want Hydracept to do the same.
- `ProductionAsset` — a durable artifact is the deliverable.

`ProductionAsset` on a synchronous invoke is unusual and is flagged as such; durable jobs are the right shape for artifacts.

## Building against these rules

A pattern that holds up:

1. **Classify in the product, not at the API boundary.** Decide the classification where you know what the data is, and pass that value through unchanged. Do not infer it from a prompt scan.
2. **Fail closed on every non-success.** `processing_not_permitted`, `processing_route_unavailable`, and `classification_downgrade_rejected` all mean "do not proceed with this data on this route." They are not retryable and there is no silent fallback to an unapproved route.
3. **Keep restricted data out of identifiers.** Do not put names, addresses, or transcript text into idempotency keys, external references, tags, or metric labels. Hydracept does not send `externalRef`, `tags`, or `metadata` to providers, but your own telemetry and logs are your responsibility.
4. **Treat a provider failure as unknown, not as approval.** If a classifier or an ingestion route is unavailable, the safe outcome is a safe fallback in your product — never an unmoderated or unverified pass-through.
5. **Verify provider eligibility yourself when you introduce a new dependency.** Hydracept's route approvals cover Hydracept's dispatch. Any third-party service your product calls directly is outside them.

## Related

- [Moderation and text classification](../moderation/) — the classification capability and its evidence shape
- [Capabilities](../capabilities/) — discovery, quotes, and pinning
- [Security](../security/) — credentials, transport, and the consumer boundary
- [Errors](../errors/) — the public error envelope and retry semantics
- [Privacy](https://hydracept.com/privacy.html) and [Terms](https://hydracept.com/terms.html)
