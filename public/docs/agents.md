# Coding Agents

Integrate Hydracept from public discovery surfaces—the published docs, OpenAPI, and agent-context endpoints. Do not rely on this monorepo or private operator docs.

## Agent context

```http
GET /v1/agent-context
```

Returns product positioning, launch capabilities, integration policy, SDK names, configuration env vars, and public path hints.

## Well-known manifests

| URL | Purpose |
|-----|---------|
| [https://hydracept.com/.well-known/hydracept.json](https://hydracept.com/.well-known/hydracept.json) | Product manifest (API, capabilities, pricing flags) |
| [https://hydracept.com/.well-known/agent-context.json](https://hydracept.com/.well-known/agent-context.json) | Agent-oriented discovery document |
| [https://hydracept.com/llms.txt](https://hydracept.com/llms.txt) | Compact guidance for LLM crawlers |

## Public OpenAPI

Canonical customer contract:

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)

Use Bearer `HydraceptApiKey` security as declared in that document. Treat internal FastAPI `/docs` schemas as operator-only—not the integration contract.

## Consumer boundary

Follow [Consumer Boundary](../consumer-boundary/). When the Hydracept CLI is available, run `hydracept consumer-check --strict` in product CI.

<!-- docs:if packages.cli.releasePublished -->
```bash
hydracept consumer-check --strict
```
<!-- docs:endif -->

<!-- docs:if packages.mcp.live -->
## MCP

Hydracept exposes an MCP server for tool-using agents. Follow the live MCP setup published with the public release.
<!-- docs:endif -->

## Clean-room path (public surface only)

1. Find Hydracept via [https://hydracept.com](https://hydracept.com) or [docs](https://docs.hydracept.com/)
2. Follow [5-minute game asset](../five-minute-game-asset/) or Quick Start + Authentication
3. Activate at `/start` or via `python -m hydracept login` (device page at `/device`)
4. Connect BYOK provider credentials before cloud inference jobs
5. Discover `image.generate.v1` via `GET /v1/capabilities`
6. Submit and poll a durable job per [Jobs](../jobs/) using the public OpenAPI
7. Confirm error and rate-limit handling from [Errors](../errors/) and [Rate limits](../rate-limits/)
