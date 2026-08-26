# Image production

Hydracept returns **assets ready for your workflow**.

Search terms teams actually use: **sprite sheet AI**, **transparent PNG generation**, **pixel art animation frames**, **inventory icon packs**, **contact sheet slice**, **chroma key matte for games**.

For `image.generate.v1`, that means transparent PNGs, cohesive multi-asset sheets, variant sets, and centered frames you can use in Unity, Godot, Unreal, or a web pipeline.

## Three production modes

| Mode | Request | You get |
|------|---------|---------|
| **Transparent output** | `requestTransparentOutput: true` | Clean alpha PNG (native or matte-normalized) |
| **Sheet & Slice** | `sheet.slice: true` with `rows` / `columns` | One cohesive generation → N centered assets |
| **Variants** | `variantCount` (2–4) | Multiple takes in one job → compare and select |

Best for **sprite sheets, pixel art animation, character poses, inventory icons, item families, VFX frames, prop packs, and UI glyphs** — small-format assets where intra-set cohesion matters more than hero-resolution detail.

## Sheet & Slice

Describe a cohesive set once. Hydracept generates a single composition, mattes the chroma plate, grid-slices (with blob fallback if the layout is skewed), centers each cell, and returns individual artifacts.

`sheet.labels` are **metadata only** — they identify cells in the API response and never appear in the provider prompt or on the generated image.

![SNES sword swing sheet after matte processing](../assets/showcase/sheet-4x4-source.png)

*Example: SNES knight sword-swing sheet (gpt-image-2), matte-processed — hover the homepage demo to compare chroma vs transparency.*

![Sword swing preview from sliced frames](../assets/showcase/sword-swing-preview.gif)

*Aligned GIF preview built from sliced transparent frames of the same job.*

### Request

```json
{
  "context": {
    "productId": "my-game",
    "projectId": "cpr_...",
    "environment": "development"
  },
  "input": {
    "prompt": "SNES-era pixel art knight sword swing animation",
    "requestTransparentOutput": true,
    "sheet": {
      "rows": 4,
      "columns": 4,
      "slice": true,
      "animation": { "facing": "right" },
      "labels": [
        "frame-01", "frame-02", "frame-03", "frame-04",
        "frame-05", "frame-06", "frame-07", "frame-08",
        "frame-09", "frame-10", "frame-11", "frame-12",
        "frame-13", "frame-14", "frame-15", "frame-16"
      ],
      "normalize": {
        "width": 256,
        "height": 256,
        "center": true
      }
    }
  },
  "execution": { "executionPreference": "automatic" },
  "idempotencyKey": "sword-swing-sheet-1"
}
```

Submit as a durable job:

```http
POST /v1/capabilities/image.generate.v1/jobs
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

### Behavior

- `sheet.labels` optionally name each cell in the API response (`frame-01`, `slash-b`, etc.). They are **not** sent to the provider and must not be drawn on the image. Succeeded jobs expose every cell on `GET /v1/jobs/{jobId}` as its own artifact with `label`, `filename`, and `sliceCellId`.
- `sheet.animation` requests subtle frame-to-frame motion with a locked facing direction.
- `sheet.slice` must be `true` to activate slicing.
- `sheet.normalize` sets the output canvas per cell (`width`, `height`, `center`). `center` trims and centers each grid cell; it does not switch the slicer to blob detection.
- `variantCount` must be `1` when sheet slicing is enabled.
- Hydracept uses provider-native transparency when available and matte normalization when needed.

### Output

A succeeded job returns **multiple artifacts** — one per sliced cell — on the job resource. Download each with:

```http
GET /v1/jobs/{jobId}/artifacts/{artifactId}
```

## Transparent output

For a single asset:

```json
{
  "input": {
    "prompt": "pixel art healing potion icon, isolated",
    "requestTransparentOutput": true
  }
}
```

Hydracept treats transparency as an **output contract**: native alpha when the provider supports it, matte normalization and validation otherwise.

## Variants

Ask for multiple creative takes in one job:

```json
{
  "input": {
    "prompt": "rusted plasma wrench inventory icon",
    "variantCount": 4,
    "requestTransparentOutput": true
  }
}
```

Poll the job, compare artifacts, and keep the exact `artifactId` you want. Provenance stays on the job receipt.

## When to use sheets vs variants

| Use sheets when… | Use variants when… |
|------------------|-------------------|
| You need **cohesion** across a set (animation frames, icon family) | You want **creative alternatives** for the same prompt |
| Objects share palette, lighting, and scale language | You will pick one winner and discard the rest |
| Output is many small assets from one generation | Output is one chosen asset from several attempts |

Sheets share one canvas, so they are ideal for sprites, icons, and other related asset sets.

## Contract sources

- Capability input schema: `GET /v1/capabilities/image.generate.v1` and [agent context](https://hydracept.com/.well-known/agent-context.json)
- Job lifecycle: [Durable Jobs & Receipts](../jobs/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
