# Coding agent integrations

Use **`hydracept-agent-plugin`** to give coding agents access to Hydracept capabilities, job submission, and result records.

Marketplace packaging is a **distribution layer** compiled from `public/agents/source/` into native host projections and the public catalog repo `zencodeinc/hydracept-agent-plugins`. The CLI (`python -m hydracept agents install --auto`) remains the universal local fallback.

## What agents can do

Agents can discover available capabilities, submit generation jobs, check progress, and retrieve artifacts and execution records.

Canonical listing copy:

> Hydracept gives game teams production-ready assets through one API. Every job leaves a receipt.

Plugin homepage (Cursor / Claude / MCP listing forms):

[https://hydracept.com/plugin](https://hydracept.com/plugin)

Official MCP Registry `description` (≤100 characters):

> AI execution infrastructure for games and agent-built software.

Publisher: **Zencode Consulting Inc.**

## Versioning

All marketplace artifacts share `distributionVersion` from `public/agents/source/identity.yaml`. Do not derive it from the Python SDK version. MCP Registry publications are immutable per version; bump `distributionVersion` before republishing metadata.

## MCP transports

| Transport | When to use | Endpoint |
|-----------|-------------|----------|
| Stdio (primary for coding agents) | Git checkout after `hydracept init` | `python -m hydracept mcp serve` |
| Hosted | No project checkout (ChatGPT, MCP Registry) | `https://api.hydracept.com/mcp` |

Stdio authenticates with `.hydracept/secrets.json`. Do not copy that key into plugin **Configure** UI. Hosted MCP authenticates with `Authorization: Bearer <HYDRACEPT_API_KEY>` for clients that cannot see the workspace:

| Host | Coding-agent auth | No-checkout auth |
|------|-------------------|------------------|
| Cursor / Claude Code | Project stdio MCP after init | Hosted MCP bearer (plugin/registry) |
| MCP Registry | n/a | `Bearer {HYDRACEPT_API_KEY}` |

## Build projections

```bash
python scripts/build_agent_distributions.py
python scripts/validate_agent_distributions.py
```

Outputs under `dist/`:

- `cursor/` — Cursor Plugin
- `claude/` — Claude Code plugin
- `agent-plugins-repo/` — public catalog assembly for `zencodeinc/hydracept-agent-plugins`
- `mcp-registry/server.json` — Official MCP Registry metadata
- `agent-plugins/` — Agent Plugins 1.0 projection
- `openai/` / `openclaw/` — later channels (not this push)

`dist/agent-plugins-repo.sha256` is the tested-bytes hash. `scripts/sync_agent_plugins.py` must push that tree unchanged (it never rebuilds).

## Install

```bash
python -m hydracept agents install --auto
```

| Host | Path |
|------|------|
| Plugin homepage | [https://hydracept.com/plugin](https://hydracept.com/plugin) |
| CLI (all hosts) | `python -m hydracept agents install --auto` |
| Cursor | Cursor Marketplace listing of `zencodeinc/hydracept-agent-plugins`, or enable `plugins/cursor` |
| Claude Code | `/plugin marketplace add zencodeinc/hydracept-agent-plugins` then `/plugin install hydracept@hydracept` |
| MCP Registry | `com.hydracept/mcp` at `https://api.hydracept.com/mcp` |

Do not document `/plugin install hydracept` as the canonical Claude form. The marketplace name (`hydracept`) participates in install.

## Verify the connection

1. Run `python -m hydracept init` in your project (CLI `0.3.0` contract). Init binds project MCP to stdio. Reload MCP once. Do not copy the workspace key into host plugin settings.
2. Ask the agent to list Hydracept capabilities (`hydracept_capabilities`).
3. Run `python -m hydracept smoke` when you want a paid verification job.

## Release invariant

```text
canonical agent source
  → build Cursor / Claude / MCP projections
  → assemble agent-plugins repo
  → validate official schemas + internal invariants
  → validate host tools where available
  → hash assembled tree
  → install generated Cursor plugin into isolated project
  → zero-knowledge marketplace-first benchmark
  → consumer-check --strict
  → export exact tested bytes to zencodeinc/hydracept-agent-plugins
  → owner publication/submission
```

## Owner checklist (this push)

- [x] Create public GitHub repo `zencodeinc/hydracept-agent-plugins`
- [x] Run `python scripts/generate_mcp_registry_http_auth.py` and backup `.hydracept/mcp-registry-http.pem` locally (do **not** put it in GitHub secrets yet)
- [x] Deploy `https://hydracept.com/.well-known/mcp-registry-auth`
- [x] After marketplace-first benchmark: `python scripts/sync_agent_plugins.py --tag v0.1.3` (do not retag `v0.1.0`, `v0.1.1`, or `v0.1.2`)
- [ ] Submit `zencodeinc/hydracept-agent-plugins` at [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish)
- [ ] Run `mcp-publisher login http --domain hydracept.com` + `mcp-publisher publish` from `dist/mcp-registry/` (private key stays local)
- [ ] Record listing URLs in `architecture/hydracept-launch-gate.yaml` → `marketplace_listings`

**Later (not this push):** submit Hydracept to Anthropic's official third-party plugin directory after the self-hosted Claude marketplace is proven.

OpenAI/Codex, ClawHub, VS Code, JetBrains, and Unity Asset Store listings are out of scope for this push.
