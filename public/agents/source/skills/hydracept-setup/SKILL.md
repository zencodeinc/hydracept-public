---
name: hydracept-setup
description: >
  Bootstrap Hydracept in a coding-agent workspace. Use when installing the CLI,
  running init, or binding stdio MCP. Never paste secrets into chat.
---

# Hydracept Setup

CLI-first bootstrap for Hydracept in a coding-agent checkout.

## Flow

If the user already asked for a capability, prefer `python -m hydracept run <key> --prompt "..."` — it composes `init` automatically. Do not run a separate setup ceremony first unless `run` returns `interaction_required`.

1. Check whether the Hydracept CLI is installed: `python -m hydracept --help`
2. If missing, explain the install path and ask for approval before running any install command.
3. Prefer the latest published Hydracept CLI. Outside this checkout, use `pip install -U hydracept`. Do not pin setup instructions to an old patch release; rely on the versioned machine contracts instead.
4. Run `python -m hydracept init --apply --yes --json`.
5. If status is `interaction_required`, **stop automation at that boundary**:
   - Do not start `--wait`, `doctor`, `consumer-check`, status checks, or other diagnostics before the human completes activation.
   - If `presentation.agentAction` is `present_and_yield` (or `interaction.surface` is `project.connect`) and `hydracept_interaction_surface` is available, invoke it once using the supplied context and stop the turn. Do not continue with other tools or a written assessment until the human completes the interaction.
   - Otherwise present `action.url` **verbatim** and stop. Do not construct, shorten, normalize, replace, or guess the URL.
   - If the human uses multiple GitHub or Google accounts, tell them to choose the intended account on the connect page.
   - Only after the human confirms completion, run the exact `afterCompletion.command` returned by init (normally `python -m hydracept init --apply --yes --json --wait`).
6. When status is `ready`, read `mcp`. `reloadRequired` is true only when MCP registration files changed — not when `secrets.json` appeared. Stdio uses `.hydracept/secrets.json` on every tool call.
7. Unattended / CI: set `HYDRACEPT_API_KEY` out of band and use `init --apply --yes --json` or `--ci`.
8. If `hydracept_*` MCP tools are missing, do not retry hosted discovery — use `python -m hydracept mcp serve --workspace ${workspaceFolder}` or `jobs submit`. Offer `/hydracept-smoke` only when asked.
9. For project surfaces: in the project repo, use stdio MCP `hydracept_project_up_install` or `python -m hydracept project up --install`. Hosted MCP cannot apply or execute local argv.

Do **not** finish setup by copying the workspace key into **Plugins → Configure**.

## Safety

- Prefer CLI help, `doctor --json`, `agent-status`, live `GET /v1/agent-context`, and public docs over inspecting Hydracept implementation source.
- Never solicit credentials in conversation.
- Never echo secrets from terminal output into chat.
- Do not inspect provider credential values in `.env` files — let `init` handle discovery.
