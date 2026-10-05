# Migrating to Hydracept 0.5.0

Hydracept **0.5.0** is a breaking client and HTTP contract release. Upgrade all SDKs and the PyPI CLI to **>= 0.5.0** before calling production.

## Upgrade packages

```bash
pip install -U "hydracept>=0.5.0"
npm install @hydracept/sdk@^0.5.0
# NuGet: Hydracept.Client 0.5.0+
```

Reload stdio MCP after upgrading the Python package.

## `hydracept init` provider keys (0.5.1)

`hydracept init --apply --yes` **does not** upload provider API keys from your laptop unless you opt in:

- **`--adopt-keys`** — upload every provider key discovered locally; or use **`--adopt-key-providers`** with a comma list.
- **`--no-adopt`** — never upload during init (default when neither flag is set).

Init prints how many keys were found but not uploaded. Adoption requires a browser session or setup grant (API-key-only init will not silently adopt).

## Wallet `consumedMicros` vs receipt cents

The wallet API reports **exact micro-USD debits** (`consumedMicros`, `availableMicros`). Receipt `pricing.actualCharge` may round to **ceiling cents** for display. Sub‑~1,500 micro-USD retail usage can be **free-absorbed** (no wallet consume transaction) while still succeeding.

## HTTP route changes

| Removed (410 `LEGACY_ROUTE_REMOVED`) | Use instead |
|--------------------------------------|-------------|
| `POST /v1/invocations` | `POST /v1/capabilities/{key}/invoke` |
| `POST /v1/jobs` (legacy) | `POST /v1/capabilities/{key}/jobs` |
| `GET /v1/invocations/{id}` | `GET /v1/jobs/{jobId}` |
| `GET /v1/invocations/{id}/receipt` | `GET /v1/jobs/{jobId}/receipt` |
| `POST /v1/invocations/{id}/cancel` | `POST /v1/jobs/{jobId}/cancel` |
| `GET /v1/invocations/{id}/events` (SSE) | `GET /v1/executions/{executionId}/events` |

410 responses include a machine-readable `code` of `LEGACY_ROUTE_REMOVED`, a concrete `use` path (for example `GET /v1/executions/fex_01234567890123456789012345/events`), and `"retryable": false`.

## Streaming (SSE)

Stream invoke token events:

```http
GET /v1/executions/{executionId}/events
Authorization: Bearer <HYDRACEPT_API_KEY>
Accept: text/event-stream
```

Durable job lifecycle history remains on `GET /v1/jobs/{jobId}/events` (cursor poll).

Python: `iter_execution_stream_events` · TypeScript: `iterExecutionStreamEvents` / `runtime.streamExecutionEvents` · .NET: `StreamExecutionEventsAsync`.

## CLI removals

Top-level `hydracept invoke`, `hydracept job`, and `hydracept receipt` were removed. Use `hydracept run`, `hydracept jobs submit`, and job inspect/receipt commands on unified job routes.

## SDK removals

Legacy helpers (`runtime.invoke`, `submitJob`, invocation GET/cancel/receipt helpers) were removed from the TypeScript, Python, and .NET clients.

See the [public changelog](https://hydracept.com/changelog/) and [Errors](../errors/) for `LEGACY_ROUTE_REMOVED`.
