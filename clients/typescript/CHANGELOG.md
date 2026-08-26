# Changelog

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
