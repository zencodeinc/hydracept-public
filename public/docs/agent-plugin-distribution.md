# Coding agent integrations

Use **`hydracept-agent-plugin`** to give coding agents access to Hydracept capabilities, job submission, and result records.

The CLI (`python -m hydracept agents install --auto`) is the universal local install. The canonical Cursor plugin repo is [github.com/zencodeinc/hydracept-plugin](https://github.com/zencodeinc/hydracept-plugin) (v0.1.10).

## What agents can do

Agents can discover available capabilities, submit generation jobs, check progress, and retrieve artifacts and execution records.

> Hydracept gives software and agents external capabilities through one stable execution control plane. Every run leaves a receipt.

Plugin homepage (Cursor / Claude / MCP listing forms):

[https://hydracept.com/plugin](https://hydracept.com/plugin)

Official MCP Registry `description` (≤100 characters):

> Directory-safe MCP: quote and run text/domain jobs with OAuth, receipts, BYOK.

Setup page: [https://hydracept.com/mcp-registry/](https://hydracept.com/mcp-registry/)

Publisher: **Zencode Consulting Inc.**

## MCP transports

| Transport | When to use | Endpoint |
|-----------|-------------|----------|
| Stdio (primary for coding agents) | Git checkout after `hydracept init` | `python -m hydracept mcp serve` |
| Hosted (API key) | No project checkout (API-key clients) | `https://api.hydracept.com/mcp` |
| Official MCP Registry remote | Registry clients; directory-safe OAuth | `https://api.hydracept.com/mcp/claude` |
| Claude directory | claude.ai connector | `https://api.hydracept.com/mcp/claude` (OAuth; a Hydracept API key is rejected) |
| OpenAI ChatGPT / Codex | ChatGPT Apps/Connectors + Codex remote MCP | `https://api.hydracept.com/mcp/openai` (OAuth; a Hydracept API key is rejected) |

Stdio authenticates with `.hydracept/secrets.json`. Do not copy that key into a host plugin **Configure** UI. API-key hosted MCP authenticates with `Authorization: Bearer <HYDRACEPT_API_KEY>`. The Official MCP Registry remote and Claude directory connector use OAuth at `https://api.hydracept.com/mcp/claude` (API keys rejected). See [https://hydracept.com/mcp-registry/](https://hydracept.com/mcp-registry/) and [https://hydracept.com/claude/](https://hydracept.com/claude/). The OpenAI ChatGPT/Codex connector uses OAuth at `https://api.hydracept.com/mcp/openai`. See [https://hydracept.com/openai/](https://hydracept.com/openai/).

## Install

```bash
python -m hydracept agents install --auto
```

| Host | Install |
|------|---------|
| Plugin homepage | [https://hydracept.com/plugin](https://hydracept.com/plugin) |
| CLI (all hosts) | `python -m hydracept agents install --auto` |
| Cursor | Not in the Cursor Marketplace yet — install from `zencodeinc/hydracept-plugin` (tag v0.1.10) or `python -m hydracept agents install --auto` |
| Claude Code | `github.com/zencodeinc/hydracept-plugin` (v0.1.10) or `python -m hydracept agents install --auto` |
| MCP Registry | `com.hydracept/hydracept` at `https://api.hydracept.com/mcp/claude` (OAuth) |

The marketplace name (`hydracept`) participates in the Claude install command.

## Verify the connection

1. Run `python -m hydracept init` in your project. This binds project MCP to stdio. Reload MCP once. Do not copy the workspace key into host plugin settings.
2. Ask the agent to list Hydracept capabilities (`hydracept_capabilities`).
3. Run `python -m hydracept smoke` when you want a paid verification job.

Listing submissions for OpenAI/Codex, ClawHub, VS Code, JetBrains, and the Unity Asset Store are separate publication decisions.
