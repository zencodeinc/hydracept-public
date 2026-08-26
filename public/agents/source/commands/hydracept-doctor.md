---
name: hydracept-doctor
description: Check Hydracept connection, CLI readiness, and stdio MCP bind.
---

# Hydracept doctor

Inspect whether this workspace can use Hydracept. Do not submit paid jobs.

## CLI (preferred in a repo)

```bash
python -m hydracept doctor --json
python -m hydracept agent-status --json
```

Doctor binds project MCP to stdio when possible. If JSON `mcp.reloadRequired` is true, tell the human to reload MCP once.

If the CLI is missing, say so and offer `pip install -U hydracept` after approval (0.3.2+ recommended). Do not send the user to **Plugins → Configure** as the way to authenticate a checkout.

## MCP tools

If `hydracept_*` tools are in **this** session, call `hydracept_status` / `hydracept_capabilities`. If they are missing, do not retry hosted discovery — use the CLI.

## Safety

- Never print API keys, bearer tokens, or `.env` values
- Use capability keys (`image.generate.v1`), not provider model names
- Do not call smoke unless the human explicitly asks
