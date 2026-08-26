---
name: hydracept-init
description: Bootstrap Hydracept in this project with CLI init. Binds stdio MCP to workspace secrets.
---

# Hydracept init

Bootstrap Hydracept without asking the human to paste secrets into chat.

## Preferred path (project checkout)

1. Check `python -m hydracept --help`. If missing, explain `pip install -U hydracept` (0.3.2+ recommended) and wait for approval.
2. Run `python -m hydracept init --apply --yes --json`.
3. If status is `interaction_required`, present `action.url` and wait for the human to finish the browser connect flow, then run `python -m hydracept init --apply --yes --json --wait`.
4. Ready JSON includes `mcp` (`bound`, `transport: stdio`, `projectConfig`, `reloadRequired`). If `reloadRequired` is true, tell the human to reload MCP once.
5. Unattended / CI: `HYDRACEPT_API_KEY` plus `init --apply --yes --json` or `--ci`.

Do **not** send the user to **Plugins → Configure** to finish init. That key store is not the workspace secret file.

## No-checkout clients only

Hosted MCP at `https://api.hydracept.com/mcp` is for ChatGPT and other clients with no project checkout. Coding agents in a repo use stdio.

## Safety

- Never ask the user to paste API keys in chat
- Never echo secrets from terminal output into chat
- Prefer MCP tools when they are in this session; otherwise CLI
