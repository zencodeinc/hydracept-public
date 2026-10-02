# Changelog

## 0.5.0 — 2026-10-02

**Breaking:** Removed legacy runtime helpers (`InvokeAsync`, `SubmitJobAsync`, invocation lifecycle GETs). Use capability invoke/job routes and unified `GET /v1/jobs/{jobId}` (+ receipt/cancel). Stream token SSE uses `GET /v1/executions/{executionId}/events` (`StreamExecutionEventsAsync`).
