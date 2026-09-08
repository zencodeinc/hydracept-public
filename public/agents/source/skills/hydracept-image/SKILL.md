---
name: hydracept-image
description: >
  Generate production game images through Hydracept image.generate.v1 — transparent
  sprites, icons, variants, and receipted jobs.
---

# Hydracept Image

Production image generation judgment for game assets.

## Capability

Use `image.generate.v1` through `python -m hydracept run image.generate.v1 --prompt "..."` or MCP `hydracept_run` / `hydracept_submit_job`. `run` composes workspace bootstrap when needed. If `execution.managedAvailable` is true, do not ask for a provider API key.

Use `image.generate.v1` for new images. Use `image.edit.v1` to edit an existing PNG in place:

- `sourceImage` — the canvas (provider `images.edit` image[0]), not a style reference
- `referenceImages` — 0–3 insert graphics (logo, overlay) as later image entries
- `mask` — optional PNG; alpha 0 is editable. Unmasked pixels are preserved by the provider.
- `prompt` — what to do in the editable region. Do not prepend generate-from-brief or global style.

## Generate-only options (`image.generate.v1`)

- Transparent PNG sprites/icons: `requestTransparentOutput: true`. Default is native alpha when the catalog model supports it (gpt-image-2).
- Advanced chroma-key matte: `transparencyMethod: "matte-v9"` with optional `keyColor` and `transparentRegions`. Required for models that have no native transparent background.
- Multiple takes: `variantCount` between 2 and 4
- Width/height snap up to multiples of 16. Open Graph: **1200×640** (not 1200×630)
- Sheet workflows: prefer the `hydracept-sheet` skill for cohesive families

`image.edit.v1` does not take a generate brief, global style, sheet, or transparency flag. Unmasked pixels stay because of `sourceImage` + `mask`, not prompt instructions.

## Transparency verification

**Never judge Hydracept PNG transparency from an image preview, chat thumbnail, vision description, or a generic `Read` rendering.** Hosts commonly composite transparent pixels onto black or white, and a vision model can then describe that viewer matte as a solid background even though it is not present in the PNG.

Machine evidence is authoritative:

- Smoke: trust `transparencyOk` together with `transparencyReport`.
- Local artifact: run `python -m hydracept verify <path.png> --json`.
- `transparencyReport.verdict == "valid_transparent_sprite"` means the decoded PNG passed Hydracept's full alpha/isolation/chroma-plate contract.
- Do not replace the verdict with a shortcut based only on transparent-pixel ratio or corner count; connected chroma-plate detection is also part of the contract.
- Do **not** regenerate an image solely because a preview appears to have a black or white background when the transparency report passes.

When visual human review is useful and `hydracept_interaction_surface` is available, successful image jobs include `presentation.surface=artifact.review`. Use the Hydracept App for composition/aesthetic review; use the machine report above to decide alpha correctness.

## Light professional brand prompts

Keep prompts short, product-neutral, and lighting-first. Do not name a provider.

- Logo / mark: `Clean light professional brand mark, flat vector, generous padding, no text, muted slate and white`
- Wordless icon: `Simple geometric app icon, light studio lighting, soft shadow, no lettering`
- Hero / OG: `Light professional product still, soft daylight, uncluttered desk, generous negative space, no logos or text`
- Texture / paper: `Subtle off-white paper texture, even lighting, no pattern repeat seams`

## Workflow

1. Describe the asset need in game terms, not provider terms
2. Read `pricingFactors` on `image.generate.v1`. Optional: `hydracept_quote_capability` (`POST /quote`) for a 0.3 `pricing.quote` preview. Do **not** attach a stale `execution.quoteId`.
3. Submit a job with project context from the workspace. **Omit `execution.quoteId`.** The API seals pricing at admission.
4. Poll until `succeeded`
5. Download artifacts. For transparency, use `transparencyReport` or `python -m hydracept verify <path.png> --json`; do not infer alpha from the preview.
6. If human visual review is needed, prefer `artifact.review` in the Hydracept App.
7. Keep the receipt for cost and provenance review
