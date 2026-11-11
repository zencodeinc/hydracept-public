# Building a conversational product

A turn-based conversational product — the user says or types something, gets a spoken or written answer — is a common Hydracept integration. This page covers the integration pattern, the capability boundaries that matter, and the data rules you have to satisfy before any of it can carry real user content.

It is deliberately product-agnostic. It describes how the pieces fit; your product owns the policy, the UX, and the safety gates.

## The shape of a turn

```text
client (mic / speaker / screen)
    |
    v
your backend  -- auth, rate limits, consent, profiles, turn state
    |-- classify user input            -> text.moderate.v1
    |-- generate an answer             -> a text capability
    |-- classify the generated answer  -> text.moderate.v1
    |-- speak the approved answer      -> audio.voice.generate.v1 (durable job)
    |
    v
your store  -- turn history, profile state, artifacts you choose to keep
```

Two rules make this shape work:

**Your client never calls Hydracept, and never holds provider credentials.** The backend holds the API key, decides the route and the cost ceiling, and is the only place that can enforce policy. A Hydracept key in a browser bundle, a mobile app, or a game client is a leak, not an architecture.

**The turn order is your safety contract.** Moderation before generation stops disallowed input from reaching a model. Moderation after generation stops an unsafe answer from reaching a speaker or a screen. Skipping the second call because the first one passed is the most common way this pattern is quietly broken.

## Capability boundaries

| Need | Capability | Notes |
|------|-----------|-------|
| Generate an answer | `text.general.fast.v1` and the other text capabilities | Synchronous invoke for short turns; durable jobs when you need retries or receipts |
| Classify input or output | `text.moderate.v1` | Synchronous only, free, returns evidence not a verdict. See [Moderation](../moderation/) |
| Speak approved text | `audio.voice.generate.v1` | Durable job producing an audio artifact. One job per utterance |
| Recognize speech | Not available | Hydracept publishes no speech-recognition capability. Use a product-local adapter you have verified yourself |

Two absences are worth planning around explicitly:

- **No speech recognition.** Client-side or product-local transcription is your dependency, with your own provider-eligibility and retention obligations. A transcription service that is `Commercially licensed` or `encrypted` is not thereby cleared for restricted content.
- **No incremental speech streaming for the durable voice capability.** `audio.voice.generate.v1` returns a complete artifact. Measure total job-to-playable time before you assume it is too slow; if it genuinely is, that is a product decision about a different capability, not a workaround inside this one.

Whether a capability is present at all is answered by `GET /v1/capabilities` and `GET /v1/capabilities/{key}`, not by this page. Query at runtime.

## Turns that use a durable job

Spoken output is a job, so a turn has to span both a synchronous and an asynchronous phase. The rules that keep that correct:

- **One job per utterance.** Submitting a second job because the first poll was slow doubles your cost and produces two artifacts. Poll the job you already have.
- **A stable idempotency key per turn phase.** Use the turn id plus the phase, and reuse it across retries. Mint a new key only when you intend a new execution.
- **A client-side timeout is not a cancellation.** A dropped connection or a wait timeout says nothing about whether the provider ran. Inspect the job before you resubmit.
- **Bound the spend per turn.** Set `executionConstraints.maxCostUsd` and opt into `budgetEnforcement: "prevent"` for a hard stop, or `"warn"` when you want the turn to complete and record the overage.
- **Cancellation ends playback in your product.** Billing reconciliation may continue on the server after the user stops listening.

Read `resolvedProvider`, `resolvedModel`, and `servedCandidateId` from results, and the route fields on receipts, so a turn can be explained later. If you pin a target, [pinning](../capabilities/#pin-an-exact-execution-target) guarantees that target or a failure — never a silent swap.

## Classifying each phase

Both moderation calls in the turn are the same capability with the same input shape: one string. What differs is what you do with the answer.

1. **Classify the user's input** before it reaches a generative model. A refusal here is the cheapest possible outcome.
2. **Classify the model's answer** before it reaches a speaker, a screen, or an image search. A provider failure is not an approval — a `flagged: null` or a non-`Available` result must produce a safe fallback, not a pass-through.
3. **Write the policy once and apply it to both phases.** Two different thresholds for input and output is a legitimate design decision; forgetting the output call is not.

A single `flagged` boolean cannot establish that an answer is appropriate for a particular audience. Use the per-category scores with your own context, and keep the escalation rules in your product where they can be reviewed.

## Data rules before you carry real content

Everything above is safe to build with synthetic, adult-authored fixtures. Carrying real user content — and especially content from or about a child — requires the data-handling groundwork first. See [Classification and data handling](../data-handling/) for the full rules; the essentials:

- **Declare the classification your data actually is.** `PrivateUserContent` for content belonging to an identifiable user. A weaker declaration does not make a request more likely to succeed; a project bound to a restricted floor rejects it as a downgrade.
- **`ChildDirected` is refused by default** with `403 processing_not_permitted`. There is no flag that changes that today. Do not relabel child content to get it through, and do not launch a product for children on the assumption that admission will be granted later without evidence.
- **Restricted classes need per-route approval.** Absence of approval is denial. Route eligibility is decided before any credential is read or any provider is called, so an unapproved route never produces a charge — but it also means the turn simply fails, and your product must handle that as a first-class state.
- **Retention is per payload class.** Raw audio, transcripts, synthesized audio, and receipt content each have their own mode. Choose the weakest retention that meets the obligation.
- **Keep restricted content out of identifiers.** No transcript text or personal identifiers in idempotency keys, external references, tags, or metric labels.
- **Third-party services you call directly are outside Hydracept's route approvals.** Verify each one for the content class and the market yourself.

## A safe fallback is a designed state, not an error handler

Every one of these is a normal outcome that your product must render deliberately:

| Outcome | What the user should experience |
|---------|--------------------------------|
| Input classification flags the turn | A refusal that does not echo the content back |
| Output classification flags the answer | A regenerated or replaced answer, never the flagging one |
| Classifier unavailable (`TimedOut`, `ProviderError`) | A safe fallback — not an unmoderated answer |
| `processing_not_permitted` / `processing_route_unavailable` | A clear "this cannot be processed" state, with no silent model swap |
| Budget prevented | A message that the turn could not run under the current limit |
| Job still running after your wait | Continue polling the same job; do not resubmit |

Treating any of these as an exception path that falls through to a generic success is the failure mode that matters most in a conversational product.

## Testing before launch

Build a case per row of the table above, plus: empty or silent audio, transcription uncertainty, a very long input, a duplicate submission with the same idempotency key, an over-length prompt (rejected, never truncated), an unsupported output format, and an unapproved data classification.

Assert on behaviour, not on compilation. A provider adapter that "works" because the method signature matches has not been tested — report outcome, error code, time to first usable response, total latency, cost, and audible quality for each case.

Fixtures that submit real work create real executions, receipts, and artifacts. Keep them in an isolated project, and never put real user content — and never any child content — through a test fixture.

## Related

- [Moderation and text classification](../moderation/) — input shape, categories, cost
- [Classification and data handling](../data-handling/) — classification semantics and processing profiles
- [Capabilities](../capabilities/) — discovery, quotes, pinning, and invoke vs jobs
- [Durable Jobs & Receipts](../jobs/) — polling, artifacts, and selection
- [Errors](../errors/) — codes and retry semantics
- [Billing & plans](../billing/) — managed fees and BYOK
