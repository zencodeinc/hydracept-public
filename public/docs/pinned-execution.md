# Pinned Execution

Use Pinned Execution when you need the same provider, model, API, and request settings every time. Hydracept sends the request as specified and returns an immutable execution record you can review or verify later.

Permanent path (no research alias):

```http
POST /v1/inference/pinned
GET  /v1/inference/pinned/{receipt_id}
POST /v1/inference/pinned/bulk
GET  /v1/inference/pinned/bulk/{bulk_id}
```

`POST /v1/inference/pinned/bulk` accepts a shared pin plus an `items` array. Each item is an independent pinned execution with its own receipt — concurrent ordinary pins, not a provider-native Batch API. Pins stay on **standard processing** unless the caller sets `processing: "deferred"` on an eligible OpenAI Responses pin (`service_tier=flex`, 50% of standard token rates) — same pin, one logical model execution, no truncation rewrite, no Flex→Standard fallback. Pre-inference capacity 429s and connection refusals may retry inside the admission deadline and are recorded on the receipt. Tenant identity is the customer **project**, same as `POST /v1/inference/pinned`: a project-bound API key is enough; an unbound key must send `context.projectId`. Organization is derived from that project. A client-supplied `organizationId` is not authorization. The bulk itself is a durable Temporal job on `hydracept-durable-bulk`: submit persists the bulk, starts `PinnedBulkWorkflow`, and returns `accepted` with `nextAction: poll`. Poll `GET /v1/inference/pinned/bulk/{bulk_id}` until `nextAction` is `stop` (`succeeded`, `partial`, or `failed`). The API process does not run bulk items; a replica restart or `/readyz` blip cannot cancel in-flight work. Sibling items do not share a provider attempt; a failure on one item does not retry or cancel the others. Concurrency is a sliding window: a hung in-flight item does not block later items from starting. When Flex capacity rejections spike, later submissions reduce concurrency instead of hammering the same ceiling.

Hydracept distinguishes three clocks:

1. **Execution timeout** — `limits.timeoutSeconds` (or top-level `timeoutSeconds`) is the **wall-clock** budget for one admitted provider HTTP attempt. Default and platform maximum 600s (`HYDRACEPT_PINNED_PROVIDER_TIMEOUT_SECONDS`). Trickling/thinking tokens do not extend this deadline. `processing: "deferred"` with an omitted timeout uses that same 600s max. Callers may set a lower value; a value above the platform maximum is rejected with `422`. Minimum is 30s. Connect/write/pool timeouts remain underneath as transport protections.
2. **Admission/retry deadline** — `limits.admissionDeadlineSeconds` is how long Hydracept may keep trying to get the request accepted after Flex-capacity 429s or connection refusal. Default 120s on standard pins and 900s on deferred pins. `0` means one HTTP submission. Maximum 1800s. Ambiguous failures after send (execution deadline, cancelled in-flight POST) are never retried. A durable dispatch boundary is persisted before each paid POST; unknown submission state is sealed as `TRANSPORT_AMBIGUOUS` rather than retried.
3. **Queue wait** — bulk Temporal `scheduleToStart` (default 20 minutes) plus time spent behind earlier in-flight items at the current concurrency. Recorded as `schedulerWaitMs` when known. This does not consume the execution timeout.

Connect/write/pool stay short so a failure before send is `providerSubmission: not_attempted`. A timeout or network error after send is `providerSubmission: ambiguous` and is never advertised as safely retryable. Receipts record `logicalAttempts=1` plus `providerSubmissions`, `capacityRejections`, `retryWaitMs`, `providerExecutionMs`, and `wallClockMs`. `safelyRetryable: false` means do not POST the sealed pin again. This per-item provider timeout is distinct from `bulkWait.timeoutSeconds` (client poll of the whole bulk, default 3600s).

## Semantics

- Explicit `provider` / `model` / `api` selection
- `store: false` where the pin requires it
- Eligible OpenAI Responses pins stay on standard processing unless `processing: "deferred"` is set (`service_tier=flex`, 50% off). One logical model execution. No truncation rewrite. No Flex→Standard fallback. Pre-inference capacity 429s may retry inside the admission deadline.
- DeepSeek V4.1 Flash is a second native pin: `provider=deepseek`, `model=deepseek-flash`, `api=chat-completions` or `api=responses`. Chat Completions non-thinking is native `thinking: {"type":"disabled"}`. Responses non-thinking is native `reasoning: {"effort":"none"}`, still requested as `sampling.thinking=disabled`. `reasoning_effort` stays `low` / `high` / `max`; `reasoning=off` is illegal. Chat Completions structured output is `responseFormat: {"type":"json_object"}`. Responses pins accept `json_schema` and honor `responseFormat.strict`. Flex/`deferred` and cache controls are not representable. This is not an OpenAI Responses pin.
- `tools` / `toolChoice` are forwarded onto the native provider request. Chat Completions keeps the nested `function` tool shape; Responses pins flatten it. A `tool_calls` / `function_call` finish is a successful completion. Empty assistant text with tool arguments is not `PROVIDER_EMPTY_OUTPUT`.
- `includeNativeResponse: true` retains the provider JSON on the execute result (`nativeResponse`) and on `GET /v1/inference/pinned/{receipt_id}`. Omitted or `false` omits the field. A non-boolean value is `422`. The flag is observability-only and is not part of protocol request identity.
- No sampling defaults: omitted temperature stays omitted
- The request is sent as specified, without silent model substitutions
- Correlation metadata never enters the prompt
- Missing execution evidence **fails** the request rather than producing an incomplete record
- Catalog workspace keys may run every registered capability, including `inference.pinned`. Membership is the registry, not a YAML allowlist. Admission uses the same BYOK / managed / platform path as other inference. Owner-org platform keys are enough; a per-project provider connection is not required.
- Capacity class: lightweight inference. Plan guardrails still apply

## Receipts

After completion, the execution record is **immutable**: selected settings, request hashes, attempts, usage, provider request ID, timestamps, and `providerSubmission` (`not_attempted`, `ambiguous`, or `attempted`) cannot change. Corrections are recorded separately.

`GET /v1/inference/pinned/{receipt_id}` returns that evidence after completion. Project-bound API keys can read receipts for their project; an organization on the principal is not required. Related receipts can be hashed into a run manifest; a stable pin becomes an AI lockfile. See [Execution provenance](../provenance/).

## Example

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pin": { "provider": "openai", "model": "gpt-5.6-sol", "api": "responses" },
    "isolation": "stateless",
    "instructions": "Return exactly what was asked.",
    "input": "ping"
  }' \
  https://api.hydracept.com/v1/inference/pinned
```

DeepSeek Flash, non-thinking, provider-enforced JSON:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pin": { "provider": "deepseek", "model": "deepseek-flash", "api": "chat-completions" },
    "isolation": "stateless",
    "sampling": { "thinking": "disabled" },
    "responseFormat": { "type": "json_object" },
    "instructions": "Return JSON only.",
    "input": "extract the id"
  }' \
  https://api.hydracept.com/v1/inference/pinned
```

Responses `json_schema`:

```json
{
  "pin": { "provider": "deepseek", "model": "deepseek-flash", "api": "responses" },
  "sampling": { "thinking": "disabled" },
  "responseFormat": {
    "type": "json_schema",
    "name": "extract",
    "schema": { "type": "object", "properties": { "id": { "type": "string" } } }
  },
  "instructions": "Return JSON only.",
  "input": "extract the id"
}
```

Python SDK:

```python
from hydracept import HydraceptClient
client = HydraceptClient(os.environ["HYDRACEPT_API_URL"], os.environ["HYDRACEPT_API_KEY"])
result = client.create_pinned_inference({
    "pin": {"provider": "openai", "model": "gpt-5.6-sol", "api": "responses"},
    "isolation": "stateless",
    "input": "ping",
})
receipt = client.get_pinned_receipt(result["receipt"]["receipt_id"])

bulk = client.create_pinned_inference_bulk({
    "pin": {"provider": "openai", "model": "gpt-5.6-sol", "api": "responses"},
    "isolation": "stateless",
    "concurrency": 8,
    "items": [
        {"id": "cell-1", "input": "ping"},
        {"id": "cell-2", "input": "pong"},
    ],
})
done = client.wait_pinned_bulk(bulk["bulkId"])
```

TypeScript:

```ts
await client.runtime.createPinnedInference({
  pin: { provider: "openai", model: "gpt-5.6-sol", api: "responses" },
  isolation: "stateless",
  input: "ping",
});
```

.NET:

```csharp
await client.CreatePinnedInferenceAsync(body);
```

CLI: `python -m hydracept pinned run body.json`, `python -m hydracept pinned bulk body.json --wait`, `python -m hydracept pinned get <receipt_id>`, then `python -m hydracept lockfile emit <receipt_id>` and `python -m hydracept verify`.

## Verification

To run the local protocol and integrity checks:

```bash
python -m pytest packages/contracts/tests/test_pinned_deepseek.py packages/contracts/tests/test_pinned_output_byte_identity.py apps/api/tests/test_pinned_protocol.py apps/api/tests/test_pinned_integrity.py apps/api/tests/test_pinned_native_response.py
```

An optional live comparison checks that the native request sent directly to OpenAI matches the request sent through Hydracept:

```bash
python scripts/run_pinned_live_conformance.py
```

It requires `HYDRACEPT_API_URL`, `HYDRACEPT_API_KEY`, and a connected OpenAI key.

## Related

- [Durable Jobs & Receipts](../jobs/)
- [Execution provenance](../provenance/)
- [Connections / BYOK](../connections/)
- [Billing & plans](../billing/)
