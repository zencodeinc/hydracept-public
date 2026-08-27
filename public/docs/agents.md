# Coding Agents

Coding agents can integrate Hydracept from the published docs, OpenAPI, and agent-context endpoints.

Hydracept gives game tools and backends one stable API for AI generation.

## Agent context

```http
GET /v1/agent-context
```

Returns the current capabilities, onboarding steps, SDK names, configuration variables, and integration guidance an agent needs to get started.

## Well-known manifests

| URL | Purpose |
|-----|---------|
| [https://hydracept.com/plugin](https://hydracept.com/plugin) | Plugin homepage (Cursor / Claude Code / MCP listings) |
| [https://hydracept.com/agent-game-assets](https://hydracept.com/agent-game-assets) | Canonical agent game-asset workflow (Cursor/Claude → reference → sheet → Unity) |
| [https://hydracept.com/.well-known/hydracept.json](https://hydracept.com/.well-known/hydracept.json) | Product manifest (API, capabilities, pricing flags) |
| [https://hydracept.com/.well-known/agent-context.json](https://hydracept.com/.well-known/agent-context.json) | Agent-oriented discovery document |
| [https://hydracept.com/llms.txt](https://hydracept.com/llms.txt) | Compact guidance for LLM crawlers |

## Public OpenAPI

Canonical customer contract:

[https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)

Authenticate requests with `Authorization: Bearer <HYDRACEPT_API_KEY>` as declared in the OpenAPI document.

## Safe integration

For products that use Hydracept for generation, follow [Integrating safely](../consumer-boundary/). You can run `python -m hydracept consumer-check --strict` in product CI.

<!-- docs:if packages.cli.releasePublished -->
```bash
python -m hydracept consumer-check --strict
```
<!-- docs:endif -->

<!-- docs:if packages.mcp.live -->
## MCP

Hydracept exposes an MCP server for tool-using agents. **In a project checkout, stdio is the default** after `python -m hydracept init`: `python -m hydracept mcp bind` writes `.cursor/mcp.json` and `.mcp.json` so `python -m hydracept mcp serve` uses `.hydracept/secrets.json`. Reload MCP once. Do not copy the workspace key into **Plugins → Configure**. Hosted endpoint `https://api.hydracept.com/mcp` is for clients with no checkout. If `hydracept_*` tools are missing, do **not** retry hosted discovery — use stdio or `python -m hydracept jobs submit`. The contract floor is CLI `0.3.0`; install `pip install -U hydracept` (0.3.1+ compares receipt SHA-256 as hex). Hosted MCP cannot apply local project files. Do not treat a cached `.hydracept/agent-context.json` as the capability catalog.

Install into a coding agent:

- **Plugin homepage:** [https://hydracept.com/plugin](https://hydracept.com/plugin)
- **Cursor:** install Hydracept from the Cursor Marketplace when listed, or add `github.com/zencodeinc/hydracept-agent-plugins`. Then `python -m hydracept init --apply --yes --json` and reload MCP.
- **Claude Code:** `/plugin marketplace add zencodeinc/hydracept-agent-plugins` then `/plugin install hydracept@hydracept`. Init in the repo and reload MCP.
- **No checkout (ChatGPT, MCP Registry):** hosted MCP at `https://api.hydracept.com/mcp` with a bearer API key
- **CLI fallback:** `python -m hydracept agents install --auto` / `python -m hydracept mcp serve` / `jobs submit`

See [Agent plugin distribution](../agent-plugin-distribution/).
<!-- docs:endif -->

## Recommended agent path

1. Read `GET /v1/agent-context` (bootstrap command and rules)
2. Run `python -m hydracept init --apply --yes --json` in the project root
3. If status is `interaction_required`, have the human open `action.url` (connect page) and re-run `init`
4. Connect BYOK for sustained inference (lazy during `init`, or Studio **Connections**), or fund a [managed inference wallet](../billing/) for PAYG generation
5. For managed inference (music, image, text, video, 3D): submit the job **without** `execution.quoteId`. The API seals pricing at admission. `/quote` is an optional preview; do not reuse a stale `quoteId`.
6. For image production (Sheet & Slice, transparency, variants), read [Image production](../image-production/). Each slice needs ≥ 655360 px and 16-aligned edges (minimum 816×816 per slice; 2×2 sheets ≥ 1632×1632).
7. For Unity 6 Editor integration, read [Unity integration](../unity-integration/)
8. Submit and poll a durable job per [Jobs](../jobs/) using the public OpenAPI
9. Confirm error / rate-limit handling from [Errors](../errors/) and [Rate limits](../rate-limits/)

## If the user asks for game image features

| User intent | Hydracept surface |
|-------------|-------------------|
| Transparent sprite / icon PNG | `image.generate.v1` + `requestTransparentOutput: true` |
| Sprite sheet / contact sheet → individual frames | `sheet.slice`, `sheet.rows`, `sheet.columns`, optional `sheet.animation` |
| Unity 6 Editor import with provenance | [Unity integration](../unity-integration/) — `hydracept integrations install unity` |
| Multiple icon takes to pick from | `variantCount` 2–4 |
| Automated art pipeline / CI | `POST /v1/capabilities/image.generate.v1/jobs` + artifact download |

Do not invent Studio-only endpoints. Prefer the public capability job contract above.
