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
- `python -m hydracept agents install --auto --smoke`

## Steps

1. Confirm local readiness with `python -m hydracept agent-status --json`
2. Run MCP `hydracept_smoke` or `python -m hydracept smoke`
3. Download the first artifact to `.hydracept/demo/first-asset.png`
4. For transparent PNGs, report `transparencyOk` and the machine evidence in `transparencyReport`. **Never judge alpha from the image preview, chat thumbnail, generic `Read`, or vision description**; hosts may composite transparent pixels onto a black or white matte. A passing `transparencyReport.verdict == "valid_transparent_sprite"` is authoritative.
5. Show the image path, receipt id, latency, and cost when available. Successful visual smoke results include `presentation.surface=artifact.review`. If the Hydracept App is available, that is the review surface; use it for composition/aesthetics, not for overriding machine alpha evidence.
6. Summarize job id and artifact ids for follow-up work

If a local byte-level recheck is needed, run `python -m hydracept verify .hydracept/demo/first-asset.png --json` rather than interpreting the preview.

## Default capability

`image.generate.v1` with a simple flat game-art prompt.
