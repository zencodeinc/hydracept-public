# Bake-offs (model comparisons)

Hydracept **Bake-offs** run the same generation intent across multiple providers or recipe variants, then capture your judgement. The API resource is called a **comparison**.

## Create a provider bake-off (image)

```http
POST /v1/capabilities/image.generate.v1/comparisons
```

```json
{
  "context": {
    "productId": "your-product",
    "environment": "development",
    "projectId": "your-project"
  },
  "input": {
    "prompt": "isolated game prop, red potion bottle",
    "width": 1024,
    "height": 1024,
    "variantCount": 1,
    "requestTransparentOutput": true
  },
  "competitors": [
    { "axis": "provider", "providerPin": "openai-image" },
    { "axis": "provider", "providerPin": "google-image" }
  ],
  "idempotencyKey": "bakeoff-potion-v1"
}
```

Each competitor becomes a normal `wfr_*` job with its own receipt and cost. Provider/model identity is hidden until you submit a judgement.

## Estimate cost

```http
POST /v1/capabilities/image.generate.v1/comparisons/estimate
```

Body: `{ "input": { ... }, "competitors": [ ... ] }`

## Poll and judge

```http
GET /v1/comparisons/{comparisonId}
POST /v1/comparisons/{comparisonId}/judgements
```

Judgement body:

```json
{
  "decision": "winner",
  "overallWinnerEntryId": "cent_…",
  "valueWinnerEntryId": "cent_…"
}
```

After judgement, the response reveals provider, model, and cost for each candidate.

## Recipe bake-off (audio SFX)

When only one provider is available, compare input variants:

```json
{
  "competitors": [
    { "axis": "recipe", "label": "500ms", "inputOverrides": { "durationMs": 500 } },
    { "axis": "recipe", "label": "2000ms", "inputOverrides": { "durationMs": 2000 } }
  ]
}
```

## SDK

TypeScript (`@hydracept/sdk`):

```ts
await client.runtime.createComparison('image.generate.v1', body);
await client.runtime.getComparison(comparisonId);
await client.runtime.submitComparisonJudgement(comparisonId, { decision: 'winner', overallWinnerEntryId });
```
