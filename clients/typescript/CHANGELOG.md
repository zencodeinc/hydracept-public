# Changelog

## 0.3.5 — 2026-09-04

- Align public SDK release with Hydracept 0.3.9 constellation (init auto-bind, vendored MCP surface catalog)

## 0.3.4 — 2026-09-03

- Align public SDK release with Hydracept 0.3.8 constellation (MCP interaction surfaces, image.edit.v1, deferred processing docs)
- Job/receipt helpers stay on `hydracept.run-result.v1`; stale quoteId omission unchanged from 0.3.1

## 0.3.3 — 2026-08-26

- Public product shape: `run`, `context`, `doctor --fix`, `jobs recover`, `funding`
- `hydracept.run-result.v1` façade across CLI / SDK / MCP
- Server-authoritative `maxCost` admission; `FundingRequired` machine error

## 0.3.2 — 2026-08-26

- Ship with the 0.3.2 public-install constellation (receipt `pricing.charge`, first-success smoke)

## 0.3.1 — 2026-08-26

- Job downloads compare receipt SHA-256 as hex (`sha256:<hex>` prefix is stripped)
- High-level submit omits stale `execution.quoteId` / `estimateId`
- Audio downloads add `.ogg` when the receipt has no filename

## 0.2.3 — 2026-08-13

- Pinned Execution: `createPinnedInference`, `getPinnedReceipt`, `listPinnedReceipts`
- Provenance: `createRunManifest`, `getRunManifest`, `verifyRunManifest`, `getLockfile`, `verifyLockfile`

## 0.2.2 — 2026-08-12

- Typed panel definition list response: `{ definitions: PanelDefinitionView[] }`
- Typed `createPanelSession` → `PanelSessionCreated`
- Exported `PanelDefinitionView`, `PanelDefinitionListResponse`, `PanelSessionCreated`

## 0.2.1

Prior release.
