# Export provenance (passive attribution)

Hydracept can embed neutral first-party metadata in PNG and GLB **at download time**. Stored artifacts in the blob store are never modified.

## Neutral generator identification

By default (org/project policy), downloads that opt into export metadata include:

- PNG: a `Software: Hydracept` tEXt chunk before `IEND` (non-destructive).
- GLB: `asset.generator` appended with `(Hydracept)`.

Opt out per organization (`neutralGeneratorIdentificationEnabled: false` in limit overrides) or project (`exportSettings.neutralGeneratorIdentificationEnabled: false`).

## Public receipt URL in files

Embedding `https://hydracept.com/r/{receiptId}` in PNG/GLB requires:

1. Project **`exportSettings.includeVerifiableProvenanceInExports`** (master switch), and
2. This job opted in via **`?includeVerifiableProvenance=true`** on an artifact GET (once per job), and
3. Export metadata applied on that download (`X-Hydracept-Export-Metadata: 1` or `?exportMetadata=1`).

Public verification is available at `GET /v1/public/receipts/{receiptId}` only while the project switch is on and the job is not revoked. Owners can revoke with `DELETE /v1/jobs/{jobId}/public-receipt-verification`.

## SDK and CLI downloads

**Default artifact GET responses are canonical store bytes** (matching receipt `artifact.sha256`). This keeps every published SDK and CLI version working.

Clients that understand export metadata send **`X-Hydracept-Export-Metadata: 1`** and verify **`X-Hydracept-Export-Sha256`** / receipt **`exportSha256`** when present.

Studio and in-browser previews use **`?exportMetadata=1`** on artifact URLs so customer-facing files still receive generator metadata by default.
