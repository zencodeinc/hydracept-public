# Changelog

## 0.5.4 (unreleased)

- Version aligned with the Python client 0.5.4. No .NET SDK API changes in this release.

## 0.5.3 (unreleased)

- Version aligned with the Python client 0.5.3. No .NET SDK API changes in this release.

## 0.5.2 (unreleased)

- NuGet README sample compiles (`using Hydracept.Client` and `HydraceptClient(HttpClient, options)`).
- Optional `HydraceptClient(HydraceptClientOptions)` convenience constructor for DI-free samples.
- Package includes `LICENSE`.

## 0.5.1 — 2026-10-05 (released)

- `InvokeCapabilityAsync` no longer overwrites a caller-supplied `idempotencyKey`; defaults one only when absent.

## 0.5.0 — 2026-10-02

**Breaking:** Removed legacy runtime helpers (`InvokeAsync`, `SubmitJobAsync`, invocation lifecycle GETs). Use capability invoke/job routes and unified `GET /v1/jobs/{jobId}` (+ receipt/cancel). Stream token SSE uses `GET /v1/executions/{executionId}/events` (`StreamExecutionEventsAsync`).
