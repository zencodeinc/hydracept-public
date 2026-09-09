# Changelog

## 0.1.2 — 2026-09-04

- Release cut aligned with Hydracept 0.3.9 public constellation; no breaking panel protocol changes

## 0.1.1 — 2026-09-03

- Release cut aligned with Hydracept 0.3.8 public constellation; no breaking panel protocol changes

## 0.1.0 — 2026-08-12

Initial public release — Gate 2.5 panel embed host SDK.

- `<hydracept-panel>` web component (alias: `<hydracept-generate>`)
- `PanelIframeManager` with formal `hydracept.embed.hello` → `hydracept.session` handshake
- `hydracept.panel.v1` protocol types and helpers
- Job bridge events: `hydracept.job.submitted`, `hydracept.job.completed`
- Session expiry via `hydracept.error` (`category: session_expired`)
- `DEFAULT_PANEL_EMBED_BASE_URL` (`https://api.hydracept.com`)
- `sendPrefill` / `sendTheme` host APIs
