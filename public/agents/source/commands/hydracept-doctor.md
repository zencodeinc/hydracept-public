---
name: hydracept-doctor
description: Check Hydracept connection, CLI readiness, and stdio MCP bind after canonical init.
---

# Hydracept doctor

Inspect an existing Hydracept workspace. Do not submit paid jobs. For a fresh checkout, run `python -m hydracept init --apply --yes --json` first instead of inventing `login -> init -> doctor` as the setup sequence.

## CLI

```bash
python -m hydracept doctor --json
python -m hydracept agent-status --json
```

Doctor binds project MCP to stdio when possible. If JSON `mcp.reloadRequired` is true, tell the human to reload MCP once.

If doctor reports missing authentication, onboarding, project selection, or workspace configuration, recover through canonical init:

```bash
python -m hydracept init --apply --yes --json
```

If that returns `interaction_required`, use its `action.url` verbatim and run its exact `afterCompletion.command` after the human completes the browser action. Do not substitute `/start`, `/device`, or a guessed URL.

When diagnostics report managed funding, interpret `managedCreditRemaining` as the aggregate available managed-credit balance. It may include trial, promo/operator, subscription, top-up, refund, or adjustment buckets. It is **not** evidence that the original trial grant was that amount. `managedTrialRemaining` is a deprecated compatibility alias for the same aggregate balance on older servers.

If the CLI is missing, say so and offer `pip install -U hydracept` after approval. Do not send the user to **Plugins → Configure** as the way to authenticate a checkout.

## MCP tools

If `hydracept_*` tools are in **this** session, call `hydracept_status` / `hydracept_capabilities`. If they are missing, do not retry hosted discovery — use the CLI.

## Safety

- Never print API keys, bearer tokens, or `.env` values.
- Use capability keys (`image.generate.v1`), not provider model names.
- Do not call smoke unless the human explicitly asks.
