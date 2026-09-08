# Hydracept Unity integration

Generate and import production assets directly from the Unity 6 Editor. Player builds stay independent of Hydracept.

## Install

### CLI (recommended)

```bash
python -m hydracept integrations install unity
```

This adds the package to your Unity project `Packages/manifest.json`.

<!-- docs:if packages.unity.registryPublished -->
### Package Manager (UPM)

```
https://github.com/zencodeinc/hydracept-public.git?path=/packages/unity#v0.1.0
```
<!-- docs:endif -->

<!-- docs:if !packages.unity.registryPublished -->
### Package Manager (UPM)

The public UPM package is not available for this release. Use the CLI install above.
<!-- docs:endif -->

## Setup

From your Unity project root:

```bash
python -m hydracept init --apply --yes --json
```

Open **Window → Hydracept** and click **Refresh** on the Status tab.

## Workflows

### Generate sprite

1. **Generate** tab → enter prompt and dimensions
2. Choose import profile (Sprite, Pixel Art Sprite, UI Sprite, Texture)
3. Submit → import variants when complete

### Sheet & Slice

1. **Sheet & Slice** tab → prompt, grid size, frame size
2. Submit → **Import All** imports individual sliced PNGs

A succeeded sheet job returns **one artifact per cell**, ready to import separately. See [Image production](../image-production/) for the API contract.

Imported assets land in `Assets/Generated/Hydracept/` with `hydracept.provenance.json` sidecars.

## Boundary

- Editor-only — no Runtime assembly
- No credentials in project assets
- Player builds do not include Hydracept code
- Imported assets work offline after import

Generation happens in the Editor. Credentials stay out of player builds, and imported assets continue to work offline. See [Integrating safely](../consumer-boundary/).
