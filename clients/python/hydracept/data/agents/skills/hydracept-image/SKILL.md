---
name: hydracept-image
description: >
  Generate production game images through Hydracept image.generate.v1 — transparent
  sprites, icons, variants, and receipted jobs.
---

# Hydracept Image

Production image generation judgment for game assets.

## Capability

Use `image.generate.v1` through `hydracept_submit_job`.

## Common options

- Transparent PNG sprites/icons: `requestTransparentOutput: true`
- Multiple takes: `variantCount` between 2 and 4
- Width/height snap up to multiples of 16. Open Graph: **1200×640** (not 1200×630)
- Sheet workflows: prefer the `hydracept-sheet` skill for cohesive families

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
5. Download artifacts to the workspace and inspect transparency or silhouette locally
6. Keep the receipt for cost and provenance review
