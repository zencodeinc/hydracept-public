# Pinned Execution

Use Pinned Execution when you need the same provider, model, API, and request settings every time. Hydracept sends the request as specified and returns an immutable execution record you can review or verify later.

Permanent path (no research alias):

```http
POST /v1/inference/pinned
GET  /v1/inference/pinned/{receipt_id}
```

## Semantics

- Explicit `provider` / `model` / `api` selection
- `store: false` where the pin requires it
- No sampling defaults: omitted temperature stays omitted
- The request is sent as specified, without silent model substitutions
- Correlation metadata never enters the prompt
- Missing execution evidence **fails** the request rather than producing an incomplete record
- BYOK first (OpenAI Responses). Managed pinned returns `501` until a later release
- Capacity class: lightweight inference. Plan guardrails still apply

## Receipts

After completion, the execution record is **immutable**: selected settings, request hashes, attempts, usage, provider request ID, and timestamps cannot change. Corrections are recorded separately.

`GET /v1/inference/pinned/{receipt_id}` returns that evidence after completion. Related receipts can be hashed into a run manifest; a stable pin becomes an AI lockfile. See [Execution provenance](../provenance/).

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

CLI: `python -m hydracept pinned run body.json`, `python -m hydracept pinned get <receipt_id>`, then `python -m hydracept lockfile emit <receipt_id>` and `python -m hydracept verify`.

## Verification

To run the local protocol and integrity checks:

```bash
python -m pytest apps/api/tests/test_pinned_protocol.py apps/api/tests/test_pinned_integrity.py
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
