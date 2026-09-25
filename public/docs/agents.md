# Coding Agents

Coding agents can integrate Hydracept from the published docs, OpenAPI, and agent-context endpoints.

Hydracept gives software and agents one stable execution surface for external capabilities including text/reasoning, translation, media generation, domains, and DNS. Job history is part of that public surface: an agent can find what failed or what already worked without turning the human into a job-ID clipboard.

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

Hydracept exposes an MCP server for tool-using agents. **In a project checkout, stdio is the default** after `python -m hydracept init`: `python -m hydracept mcp bind` writes `.cursor/mcp.json` and `.mcp.json` so `python -m hydracept mcp serve` uses `.hydracept/secrets.json`. Reload MCP once when init reports `reloadRequired: true`. Do not copy the workspace key into **Plugins → Configure**. Hosted endpoint `https://api.hydracept.com/mcp` is for clients with no checkout. If `hydracept_*` tools are missing, do **not** retry hosted discovery — use stdio or the CLI. Install the latest public package with `pip install -U hydracept`; rely on versioned machine contracts rather than hard-coded patch-version folklore. Hosted MCP cannot apply local project files. Do not treat a cached `.hydracept/agent-context.json` as the capability catalog.

Job recovery tools are available on both stdio and hosted MCP:

- `hydracept_jobs_find` — find recent, failed, or reusable jobs in the bound project
- `hydracept_job_inspect` — inspect one selected job's error, diagnostics, receipt summary, request snapshot, and reuse candidate

Install into a coding agent:

- **Plugin homepage:** [https://hydracept.com/plugin](https://hydracept.com/plugin)
- **Cursor:** Hydracept is not in the Cursor Marketplace yet — use [github.com/zencodeinc/hydracept-plugin](https://github.com/zencodeinc/hydracept-plugin) (v0.1.8) or `python -m hydracept agents install --auto`. Then run `python -m hydracept init --apply --yes --json` and reload MCP only when requested.
- **Claude Code:** install the Hydracept plugin, init in the repo, and reload MCP only when requested.
- **No checkout (ChatGPT, MCP Registry):** hosted MCP at `https://api.hydracept.com/mcp` with a bearer API key
- **CLI fallback:** `python -m hydracept agents install --auto` / `python -m hydracept mcp serve` / `python -m hydracept run ...`

See [Agent plugin distribution](../agent-plugin-distribution/).
<!-- docs:endif -->

## MCP interaction panel (stdio, 0.3.9+)

After `python -m hydracept init --apply --yes --json`, stdio MCP exposes `hydracept_interaction_surface` for seven semantic states of one App (`ui://hydracept/app.html`). Follow `presentation.agentAction`. `present_and_yield` means present the surface and stop the turn. `presentation.status` `mount_requested` means present the App; `mounted`/`already_mounted` means the App is the UI; `fallback`/`unsupported` means use the structured fallback. The panel is presentation-only — it does not execute, charge, or write the repository. Reload MCP after upgrading to hydracept 0.3.17+ (0.3.12+ is the floor for init to reuse `gh`/`gcloud` without a browser). Funding display in 0.3.13+ no longer labels customer-visible `$0` as aggregate/trial credit when execution is funded by operator grants. Structured capability input should be passed with `--input-file` / `--body` rather than inline JSON on PowerShell.

## Recommended agent path

1. Read `GET /v1/agent-context` for the live bootstrap command, capability catalog, and rules.
2. Run `python -m hydracept init --apply --yes --json` in the project root.
3. If status is `ready`, the JSON `project.resolution` field tells you whether Hydracept reused a binding, matched a repository, or created the workspace project.
4. If status is `interaction_required`, **stop automation immediately**. Identity may already be authenticated — read `identity` and `projectResolution` before assuming login failed. Do not start `--wait`, doctor, consumer-check, status, or unrelated diagnostics. If `presentation.agentAction` is `present_and_yield` and `hydracept_interaction_surface` is available, invoke it once with the supplied `interaction.context` and make it the final tool call of the turn. Otherwise present `action.url` verbatim and stop. Only after the human confirms completion should the agent run the returned `afterCompletion.command`.
5. Connect BYOK for sustained inference, or use managed inference. Ordinary new Free accounts receive a one-time **US$0.50 managed trial allowance** for setup/smoke verification; BYOK is 0% Hydracept fee and managed execution is provider price + 6%.
6. Discover the needed capability live. Do not assume Hydracept is only a game/media tool; the catalog may include text/reasoning, translation, domain/DNS, media, research, and other external operations.
7. Submit managed work **without** `execution.quoteId`. The API seals pricing at admission. `/quote` is an optional preview; do not reuse a stale `quoteId`.
8. For image production (Sheet & Slice, transparency, variants), read [Image production](../image-production/). Size a sheet by either the cell (`sheet.normalize.width/height`; canvas = cell × columns,rows) or the canvas (`width`/`height`; cell = canvas ÷ columns,rows); both given must agree. The resulting canvas must meet the model minimum (default 816×816, 16-aligned) and slices may be any size. Read `sheetSlicing`/`canvasFloor` on `GET /v1/capabilities/image.generate.v1`.
9. For Unity 6 Editor integration, read [Unity integration](../unity-integration/).
10. Submit and poll durable jobs per [Jobs](../jobs/) using the public capability contract.
11. If the user says **“the last job failed”**, call `hydracept_jobs_find(intent="failed")` before asking for a job ID, then `hydracept_job_inspect` on the relevant item. Read `error.code`; if retrying, use the `requestSnapshot` input with a new idempotency key.
12. If the user says **“use the one we picked”** or **“reuse the last good one”**, call `hydracept_jobs_find(intent="reusable", capability_key="...")`, inspect the candidate, and prefer its explicit `selectedArtifactId`. Do not promote, favorite, or approve it implicitly.
13. Confirm error / rate-limit handling from [Errors](../errors/) and [Rate limits](../rate-limits/).
14. For a clean-room consumer audit, run `python -m hydracept consumer-check --strict --json` and require `passed: true`.

The project list is intentionally prompt-free. Agents can scan failed and reusable jobs without ingesting every historical request. Prompt/request content appears only after the agent deliberately inspects a single job.

## If the user asks for game image features

| User intent | Hydracept surface |
|-------------|-------------------|
| Transparent sprite / icon PNG | `image.generate.v1` + `requestTransparentOutput: true` (native alpha when the catalog model supports it) |
| Full-bleed plate with interior openings | same; native alpha by default. Advanced chroma: `transparencyMethod: "matte-v9"` + `transparentRegions: "borderConnectedAndEnclosed"` |
| Force chroma-key matte | `transparencyMethod: "matte-v9"` + optional `keyColor` |
| Sprite sheet / contact sheet → individual frames | `sheet.slice`, `sheet.rows`, `sheet.columns`, optional `sheet.animation` |
| Unity 6 Editor import with provenance | [Unity integration](../unity-integration/) — `hydracept integrations install unity` |
| Multiple icon takes to pick from | `variantCount` 2–4 |
| Recover the last failed generation | `hydracept_jobs_find(intent="failed")` → `hydracept_job_inspect` |
| Reuse the selected prior artifact | `hydracept_jobs_find(intent="reusable")` → inspect → download/reference `selectedArtifactId` |
| Automated art pipeline / CI | `POST /v1/capabilities/image.generate.v1/jobs` + artifact download |

Do not invent Studio-only endpoints. Prefer the public capability contract and live catalog. Pinned research runs remain on the pinned-execution contract; project job history does not pretend to be a pinned-run history API.
