---
name: hydracept-sheet
description: >
  Generate cohesive sprite, icon, glyph, and VFX families with Hydracept Sheet &
  Slice. Use when the user needs a contact sheet or sliced frames.
---

# Hydracept Sheet

Cohesive sprite, icon, glyph, and VFX families via Sheet & Slice.

## Capability

Use `image.generate.v1` with sheet options — not a separate fictional capability.

## Pixel minimum (required)

Each **slice** (and a non-sliced image) needs **≥ 655360 total pixels**. Edges must be **multiples of 16**. Minimum square: **816×816**.

A 2×2 sheet is four slices. Do **not** submit 1024×1024 — that is 512×512 per cell (262144 px) and fails. Use at least **1632×1632** (816×816 per cell) for 2×2.

If the API returns `total pixels must be >= 655360`, the message includes this slice `W×H` and the 816×816 floor. Resize; do not retry the same canvas.

## Sheet options

- `sheet.slice`: true when individual frames are needed
- `sheet.rows` and `sheet.columns` for contact-sheet layout
- `sheet.animation` when frame order matters
- `requestTransparentOutput: true` for game-ready PNG frames

## Workflow

1. Define the family: style, count, and intended in-game use
2. Size the sheet so **each slice** meets 816×816 (or another 16-aligned pair ≥ 655360 px)
3. Submit one sheet job with consistent prompt and sheet metadata
4. Poll the job and download the sheet plus sliced frames when available
5. Prefer one cohesive sheet over many unrelated single-image jobs
6. Summarize artifact paths and receipt details for the team
