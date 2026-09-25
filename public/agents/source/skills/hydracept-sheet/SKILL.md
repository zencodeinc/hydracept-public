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

## Sizing (required)

Size the sheet by **either** axis — you do not need both:

- **Cell size** — `sheet.normalize.width/height`. The canvas is then
  `cell × columns` by `cell × rows`.
- **Canvas size** — `width`/`height`. Each cell is then
  `width ÷ columns` by `height ÷ rows`.

If you give both they must agree (`canvas = cell × columns, rows`), or the request is
rejected with the relationship spelled out.

The **resulting canvas** must meet the model's minimum canvas. This is data-driven: read
`canvasFloor` and `sheetSlicing` on `GET /v1/capabilities/image.generate.v1`.

- Edges are multiples of the model's `multipleOf` (16 for the default image model).
- Minimum square on the default model: **816×816**.
- **Slices may be any size.** There is no per-slice pixel floor; a legal canvas slices into
  whatever `rows × columns` you asked for.

Examples on the default model: 2×2 with `normalize 408×408` → canvas 816×816; 2×2 with
`width/height 1024` → cells 512×512; 4×4 with `width/height 1024` → cells 256×256 (and
smaller after trim) — all legal.

## Sheet options

- `sheet.slice`: true when individual frames are needed
- `sheet.rows` and `sheet.columns` for contact-sheet layout
- `sheet.animation` when frame order matters
- `requestTransparentOutput: true` for game-ready PNG frames

## Workflow

1. Define the family: style, count, and intended in-game use
2. Size the **sheet canvas** to meet the model minimum (default 816×816, 16-aligned)
3. Submit one sheet job with consistent prompt and sheet metadata
4. Poll the job and download the sheet plus sliced frames when available
5. Prefer one cohesive sheet over many unrelated single-image jobs
6. Summarize artifact paths and receipt details for the team
