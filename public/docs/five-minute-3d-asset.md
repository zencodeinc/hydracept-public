# 5-minute 3D asset

Generate a game-ready GLB mesh through Hydracept in about five minutes.

**BYOK:** 3D generation uses **Meshy** for mesh conversion. The `model.generate.3d.from-image.v1` pipeline also uses **OpenAI** for turnaround views. Connect both keys before running production jobs.

Hydracept is **not** a Unity/Unreal plugin. Integrate from tools and backends.

## 1. Activate

Same as the [5-minute game asset](../five-minute-game-asset/) flow:

```bash
pip install -U hydracept
python -m hydracept init --apply --yes --wait
python -m hydracept doctor
```

## 2. Connect BYOK

Open **Configure BYOK** from activation, or visit:

`https://api.hydracept.com/v1/onboarding/byok?organizationId=…&projectId=…&environment=development`

Paste:

- **OpenAI** — concept images and turnaround sheets (`model.generate.3d.from-image.v1`)
- **Meshy** — multi-image-to-3d conversion (`model.generate.3d.v1`)

See [Connections / BYOK](../connections/).

## 3. Path A — single image to GLB

Best for a first smoke when you already have a concept PNG from `image.generate.v1`:

```bash
export HYDRACEPT_API_URL=https://api.hydracept.com
# Submit image.generate.v1 first, then use the returned artifact id as baseArtifactId.
JOB_JSON=$(curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"context\": {
      \"productId\": \"demo-game\",
      \"projectId\": \"$HYDRACEPT_PROJECT\",
      \"environment\": \"$HYDRACEPT_ENVIRONMENT\"
    },
    \"input\": {
      \"baseArtifactId\": \"$BASE_ARTIFACT_ID\",
      \"meshProfile\": \"toy_default\",
      \"turnaroundMode\": \"sheet2x2\"
    },
    \"execution\": { \"executionPreference\": \"automatic\" },
    \"idempotencyKey\": \"five-minute-3d-from-image-1\"
  }" \
  "$HYDRACEPT_API_URL/v1/capabilities/model.generate.3d.from-image.v1/jobs")
```

Poll `GET /v1/jobs/{jobId}` until the status is `succeeded`, then fetch the receipt for GLB artifact download paths.

By default, public jobs **auto-approve** the turnaround sheet and continue straight to Meshy. Set `"requireTurnaroundApproval": true` when you want a review pause (Hydracept Studio / panels use this path).

## 4. Path B — turnaround views to GLB

When you already have 1–4 orthographic view images (front/left/right/back):

```bash
JOB_JSON=$(curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"context\": {
      \"productId\": \"demo-game\",
      \"projectId\": \"$HYDRACEPT_PROJECT\",
      \"environment\": \"$HYDRACEPT_ENVIRONMENT\"
    },
    \"input\": {
      \"inputArtifactIds\": [\"$VIEW_FRONT\", \"$VIEW_LEFT\", \"$VIEW_RIGHT\", \"$VIEW_BACK\"],
      \"meshProfile\": \"toy_default\"
    },
    \"execution\": { \"executionPreference\": \"automatic\" },
    \"idempotencyKey\": \"five-minute-3d-mesh-1\"
  }" \
  "$HYDRACEPT_API_URL/v1/capabilities/model.generate.3d.v1/jobs")
```

## Mesh profiles

| Profile | Use when |
|---------|----------|
| `draft_fast` | Quick iteration, lower polycount |
| `toy_default` | Stylized game toys and props |
| `clean_game_mesh` | Cleaner topology for rigging |
| `hero_hd` | Higher-detail hero assets |
| `enhanced_retry` | Retry with enhanced Meshy settings |

## What you proved

- Hydracept authenticated your caller
- Durable 3D jobs produce receipted GLB artifacts
- Provider billing stays on your OpenAI and Meshy accounts

## Next

- [Capabilities](../capabilities/)
- [Connections / BYOK](../connections/)
- [Jobs](../jobs/)
- [5-minute game asset](../five-minute-game-asset/)
