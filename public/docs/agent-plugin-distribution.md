# Coding agent integrations

Use **`hydracept-agent-plugin`** to give coding agents access to Hydracept capabilities, job submission, and result records.

The CLI (`python -m hydracept agents install --auto`) is the universal local install. Host plugins are also published from the public catalog at [github.com/zencodeinc/hydracept-agent-plugins](https://github.com/zencodeinc/hydracept-agent-plugins).

## What agents can do

Agents can discover available capabilities, submit generation jobs, check progress, and retrieve artifacts and execution records.

> Hydracept gives software and agents external capabilities through one stable execution control plane. Every run leaves a receipt.

Plugin homepage (Cursor / Claude / MCP listing forms):

[https://hydracept.com/plugin](https://hydracept.com/plugin)

Official MCP Registry `description` (≤100 characters):

> Execution control plane for agents: capabilities, durable jobs, budgets, receipts, and BYOK.

Publisher: **Zencode Consulting Inc.**

## MCP transports

| Transport | When to use | Endpoint |
|-----------|-------------|----------|
| Stdio (primary for coding agents) | Git checkout after `hydracept init` | `python -m hydracept mcp serve` |
| Hosted | No project checkout (ChatGPT, MCP Registry) | `https://api.hydracept.com/mcp` |

Stdio authenticates with `.hydracept/secrets.json`. Do not copy that key into a host plugin **Configure** UI. Hosted MCP authenticates with `Authorization: Bearer <HYDRACEPT_API_KEY>` for clients that cannot see the workspace.

## Install

```bash
python -m hydracept agents install --auto
```

| Host | Install |
|------|---------|
| Plugin homepage | [https://hydracept.com/plugin](https://hydracept.com/plugin) |
| CLI (all hosts) | `python -m hydracept agents install --auto` |
| Cursor | Cursor Marketplace listing of `zencodeinc/hydracept-agent-plugins`, or enable `plugins/cursor` |
| Claude Code | `/plugin marketplace add zencodeinc/hydracept-agent-plugins` then `/plugin install hydracept@hydracept` |
| MCP Registry | `com.hydracept/mcp` at `https://api.hydracept.com/mcp` |

The marketplace name (`hydracept`) participates in the Claude install command.

## Verify the connection

1. Run `python -m hydracept init` in your project. This binds project MCP to stdio. Reload MCP once. Do not copy the workspace key into host plugin settings.
2. Ask the agent to list Hydracept capabilities (`hydracept_capabilities`).
3. Run `python -m hydracept smoke` when you want a paid verification job.

Listing submissions for OpenAI/Codex, ClawHub, VS Code, JetBrains, and the Unity Asset Store are separate publication decisions.
