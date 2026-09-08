# Execution provenance

Know exactly what happened when an AI result was produced. Every Hydracept execution leaves a **receipt**: a durable record of the request, the execution, the provider response, and any resulting artifact.

Pinned Execution gives you the strongest form of reproducibility. Provenance helps you review results, reproduce important runs, and show what changed between them.

```text
one execution          → Receipt
many related executions → Run Manifest
stable dependency       → AI Lockfile
```

Use provenance to:

- reproduce a result with the same provider, model, and API
- review the request and execution history behind an artifact
- group related executions into an experiment, CI run, or release
- detect changes in model pins, request semantics, and provider behavior

## Receipt

A receipt answers:

- who requested it
- which provider, model, and native API
- the exact request and parameters
- whether anything was rewritten, retried, or fell back
- what the provider returned, what it cost, and which artifact resulted

Pinned receipts (`GET /v1/inference/pinned/{receipt_id}`) provide the strongest guarantee: an exact pin, native hashes, no fallback, and evidence that is immutable after completion. Routed jobs also leave receipts, including the routing Hydracept applied. Receipt funding is copied from admission evidence; missing evidence stays `unknown` and must not be inferred as BYOK or managed trial.

See [Pinned Execution](../pinned-execution/) and [Durable Jobs & Receipts](../jobs/).

## Run manifest

A run manifest hashes a set of related receipts — an experiment, a CI run, a release.

```http
POST /v1/provenance/manifests
GET  /v1/provenance/manifests/{manifest_id}
POST /v1/provenance/manifests/{manifest_id}/verify
```

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "Experiment 003",
    "receiptIds": ["rcpt_...", "rcpt_..."],
    "experimentHash": "..."
  }' \
  https://api.hydracept.com/v1/provenance/manifests
```

```bash
python -m hydracept verify run-003.manifest.json
```

Verify reports how many receipts were found, how many pins match, whether request hashes drifted, fallbacks, provider retries, and provider spend.

## AI lockfile

Software has `package-lock.json`. AI applications have their own dependencies: provider, model pin, native API, sampling semantics, and prompt or tool hashes.

```bash
python -m hydracept lockfile emit rcpt_...
python -m hydracept verify
```

`hydracept.lock` records the pin and the last receipt. `hydracept verify` checks that the model pin resolves, the native API is supported, request semantics are unchanged, credentials are available, and the latest conformance check passed.

```http
GET  /v1/provenance/lockfile?receipt_id=rcpt_...
POST /v1/provenance/lockfile/verify
```

The lockfile is derived from receipts, so your execution record and reproducibility checks stay connected.

## Related

- [Pinned Execution](../pinned-execution/)
- [Durable Jobs & Receipts](../jobs/)
- [Research Inference Protocol](../research/)
- [Connections / BYOK](../connections/)
