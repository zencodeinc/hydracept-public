# Coding Agents

Coding agents can integrate Hydracept from the published docs, OpenAPI, and agent-context endpoints.

Hydracept gives software and agents one public API for external capabilities including text, translation, media, domains, and DNS. Job history is part of that surface: an agent can find what failed or what already worked without asking the human to paste job IDs.

A single capability call is a supported usage. CI, SDK embedding, provider pinning, and production workflows are later compounding benefits — not an entrance fee.

## One capability when you need it

```bash
python -m hydracept capabilities find "generate an image"
python -m hydracept run image.generate.v1 --prompt "transparent 1024x1024 blue slime icon" --json
```

`run` composes `init` when the workspace can be bootstrapped. Do not start with a setup ceremony if the user already asked for a result.

Opportunistic examples: one transparent icon, a 2-second UI sound, a rough 3D model, a domain availability check, a short translation, a higher-quality reasoning pass.

## Agent context

```http
GET /v1/agent-context
```

Returns the current capabilities, onboarding steps, SDK names, configuration variables, and integration guidance an agent needs to get started.

Durable text jobs use [deferred processing](../deferred-processing/) at 50% of standard token rates. Prefer `POST /v1/capabilities/{key}/jobs` (or MCP `hydracept_submit_job`) when the work can wait. Pins stay one-attempt and standard unless `processing: "deferred"` is set. Discover `features.deferredProcessing` on capability descriptors.

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

For products that use Hydracept for execution, follow [Integrating safely](../consumer-boundary/). Run the strict boundary in product CI; add `--json` when an agent or CI system needs a stable machine result.

<!-- docs:if packages.cli.releasePublished -->
```bash
python -m hydracept consumer-check --strict --json
```
<!-- docs:endif -->

<!-- docs:if packages.mcp.live -->
## MCP

Hydracept exposes an MCP server for tool-using agents. **In a project checkout, stdio is the default** after `python -m hydracept init`: `python -m hydracept mcp bind` writes `.cursor/mcp.json` and `.mcp.json` so `python -m hydracept mcp serve` uses `.hydracept/secrets.json`. Reload MCP once when init reports `reloadRequired: true`. Do not copy the workspace key into **Plugins → Configure**. Hosted `https://api.hydracept.com/mcp` is for clients with no checkout and defaults to the nine-tool compact list for new API keys; use `https://api.hydracept.com/mcp/full` for all specialist tools. If you need LoRA, pinned inference, or job-history tools on hosted MCP, use `/mcp/full` or stdio. Install `pip install -U hydracept` and read `GET /v1/agent-context` for the live tool list. Hosted MCP cannot apply local project files.

Job recovery tools are available on both stdio and hosted MCP:

- `hydracept_jobs_find` — find recent, failed, or reusable jobs in the workspace-bound project. The list has no prompt text.
- `hydracept_job_inspect` — read one job. The prompt that was executed is `executedPrompt` (`requestSnapshot.input.prompt`). Text jobs return it when a prompt record was kept and no input payload was stored. Also returns error, diagnostics, receipt summary, and a reuse candidate.

Install into a coding agent:

- **Plugin homepage:** [https://hydracept.com/plugin](https://hydracept.com/plugin)
- **Cursor:** Hydracept is not in the Cursor Marketplace yet — use [github.com/zencodeinc/hydracept-plugin](https://github.com/zencodeinc/hydracept-plugin) (plugin distributionVersion **0.1.10**, separate from PyPI client **0.5.x**) or `python -m hydracept agents install --auto`. Then run `python -m hydracept init --apply --yes --json` and reload MCP only when requested.
- **Claude Code:** install the Hydracept plugin, init in the repo, and reload MCP only when requested.
- **No checkout (ChatGPT, MCP Registry):** hosted MCP at `https://api.hydracept.com/mcp` with a bearer API key
- **CLI fallback:** `python -m hydracept agents install --auto` / `python -m hydracept mcp serve` / `python -m hydracept run ...`

See [Agent plugin distribution](../agent-plugin-distribution/).
<!-- docs:endif -->

## MCP interaction panel (stdio, 0.5.0+)

After `python -m hydracept init --apply --yes --json`, stdio MCP exposes `hydracept_interaction_surface` for seven semantic states of one App (`ui://hydracept/app.html`). Follow `presentation.agentAction`. `present_and_yield` means present the surface and stop the turn. `presentation.status` `mount_requested` means present the App; `mounted`/`already_mounted` means the App is the UI; `fallback`/`unsupported` means use the structured fallback. The panel is presentation-only — it does not execute, charge, or write the repository. Reload MCP after upgrading to **hydracept 0.5.0+** (required for current HTTP routes; see [Migrating to 0.5.0](../migrating-0.5.0/)). Funding display in 0.3.13+ no longer labels customer-visible `$0` as aggregate/trial credit when execution is funded by operator grants. Structured capability input should be passed with `--input-file` / `--body` rather than inline JSON on PowerShell.

## Recommended agent path

1. `pip install -U hydracept` and read `GET /v1/agent-context` for the live bootstrap command and capability list.
2. Run `python -m hydracept init --apply --yes --json` in the project root (init may reuse `gh`, `gcloud`, or `HYDRACEPT_API_KEY` — see [Authentication](../authentication/)).
3. If init returns `interaction_required`, stop and let the human finish the browser step; do not run unrelated diagnostics in a loop.
4. Discover a capability (`python -m hydracept capabilities find "…"` or MCP `hydracept_resolve_capability`) and run it with `python -m hydracept run …` or MCP `hydracept_run`.
5. For sustained managed use, connect BYOK or fund the wallet. New Free accounts include a one-time **US$0.50** managed trial allowance; afterward managed runs bill at provider cost + **6%** Hydracept service fee (actual usage, no per-call minimum).

See [Jobs](../jobs/), [Billing](../billing/), and [Errors](../errors/) when you need durable polling, pricing detail, or failure handling.

The project list is intentionally prompt-free. Agents can scan failed and reusable jobs without ingesting every historical request. Prompt/request content appears only after the agent deliberately inspects a single job.

## If the user asks for game image features

| User intent | Hydracept surface |
|-------------|-------------------|
| Transparent sprite / icon PNG | `image.generate.v1` + `requestTransparentOutput: true` (native alpha when the catalog model supports it) |
| Full-bleed openings | `requestTransparentOutput: true`. On gpt-image models this is native alpha. `transparencyMethod: "matte-v9"` is only for models with no native alpha. |
| Chroma-key matte | `transparencyMethod: "matte-v9"` only for models with no native alpha. Ignored on gpt-image models. |
| Sprite sheet / contact sheet → individual frames | `sheet.slice`, `sheet.rows`, `sheet.columns`, optional `sheet.animation` |
| Unity 6 Editor import with provenance | [Unity integration](../unity-integration/) — `hydracept integrations install unity` |
| Multiple icon takes to pick from | `variantCount` 2–4 |
| Read the prompt that was executed | `hydracept_job_inspect(job_id)` → `executedPrompt`. Unknown id: `hydracept_jobs_find(intent="recent")` first |
| Recover the last failed generation | `hydracept_jobs_find(intent="failed")` → `hydracept_job_inspect` |
| Reuse the selected prior artifact | `hydracept_jobs_find(intent="reusable")` → inspect → download/reference `selectedArtifactId` |
| Automated art pipeline / CI | `POST /v1/capabilities/image.generate.v1/jobs` + artifact download |

Do not invent Studio-only endpoints. Prefer the public capability contract and live catalog. Pinned research runs remain on the pinned-execution contract; project job history does not pretend to be a pinned-run history API.
