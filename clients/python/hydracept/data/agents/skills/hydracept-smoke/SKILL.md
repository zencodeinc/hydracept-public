---
name: hydracept-smoke
description: >
  Run an explicit paid Hydracept first-success smoke job. Do not run automatically
  on IDE startup; only when the user asks to verify the setup.
---

# Hydracept Smoke

Explicit paid first-success verification. Do not run automatically on IDE startup.

## Allowed triggers

- `/hydracept-smoke`
- `python -m hydracept smoke`
- `python -m hydracept quickstart --smoke`
- `python -m hydracept agents install --auto --smoke`

## Steps

1. Confirm local readiness with `python -m hydracept agent-status --json`
2. Run MCP `hydracept_smoke` or `python -m hydracept smoke`
3. Download the first artifact to `.hydracept/demo/first-asset.png`
4. Show the image path, receipt id, latency, and cost when available
5. Summarize job id and artifact ids for follow-up work

## Default capability

`image.generate.v1` with a simple flat game-art prompt.
