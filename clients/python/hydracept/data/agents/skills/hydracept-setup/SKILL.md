---
name: hydracept-setup
description: >
  Bootstrap Hydracept in a coding-agent workspace. Use when installing the CLI,
  running init, or binding stdio MCP. Never paste secrets into chat.
---

# Hydracept Setup

CLI-first bootstrap for Hydracept in a coding-agent checkout.

## Flow

1. Check whether the Hydracept CLI is installed: `python -m hydracept --help`
2. If missing, explain the install path and ask for approval before running any install command
3. Verify the Hydracept CLI version is at least `0.3.0` (prefer `0.3.2` for first-success smoke evidence and receipt `pricing.charge`). In this checkout that is already true. Outside it, `pip install -U hydracept`.
4. Run `python -m hydracept init --apply --yes --json`
5. If status is `interaction_required`:
   - Present `action.url` to the human
   - If they use multiple GitHub or Google accounts, tell them to pick the correct account on the connect page
   - After they confirm browser setup, run `python -m hydracept init --apply --yes --json --wait`
6. When status is `ready`, read `mcp`. `reloadRequired` is true only when MCP registration files changed — not when `secrets.json` appeared. Stdio uses `.hydracept/secrets.json` on every tool call.
7. Unattended / CI: set `HYDRACEPT_API_KEY` and use `init --apply --yes --json` or `--ci`
8. If `hydracept_*` MCP tools are missing, do not retry hosted discovery — use `python -m hydracept mcp serve` or `jobs submit`. Offer `/hydracept-smoke` only when asked.
9. For project surfaces: in the game repo, use stdio MCP `hydracept_project_up_install` or `python -m hydracept project up --install`. Hosted MCP cannot apply or execute local argv.

Do **not** finish setup by copying the workspace key into **Plugins → Configure**.

## Safety

- Never solicit credentials in conversation
- Never echo secrets from terminal output into chat
- Do not inspect provider credential values in `.env` files — let `init` handle discovery
