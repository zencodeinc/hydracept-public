# Changelog

## 0.3.22 — 2026-09-14

- MCP workspace resolution attests runtime once per process and caches the resolved checkout (fewer Windows `mcp-runtime.json` locks)
- MCP tools accept `capability`, `capability_key`, and `capabilityKey` interchangeably
- `version --json` and doctor/agent-status include unified `packageProvenance` + workspace consumer versions
- `docs.hydracept.com/llms.txt` mirror ships with site build (same content as hydracept.com/llms.txt)

## 0.3.21 — 2026-09-14

- `text.translate.v1 --prompt` maps to `targetLocale` + `items` (`--target-locale` or `locale:text` prefix); bare prompt fails with recovery guidance instead of empty output
- Empty `typedOutput.items` on translation is surfaced as `EmptyStructuredOutput`, not silent success
- Default `run` prints translation/text previews for non-artifact capabilities
- Image `run --prompt` notes the 816×816 canvas floor before submission
- Windows MCP runtime attestation retries transient `mcp-runtime.json` file locks

## 0.3.20 — 2026-09-13

- Default `run` prints human-readable status, `pricing.summary`, and artifact paths; `--json` unchanged
- `capabilities describe` surfaces `canvasFloor` for image capabilities, deferred job latency notes, and `--prompt` CLI hints
- `hydracept.run-result.v1` pricing includes a one-line `summary` for covered vs customer-funded charges
- `llms.txt` documents Windows/PowerShell `--input-file`, customer-charge semantics, and the 816×816 image canvas floor

## 0.3.19 — 2026-09-12

- `hydracept.run-result.v1` pricing leads with `customerCharge.customerTotalMicros` (what this customer was charged)
- `jobs receipt` and MCP receipt summaries expose the same customer-charge block; estimated/retail fields stay labeled separately
- Stale stdio MCP is a warning with reload/CLI guidance, not a catastrophic doctor failure
- Installed client, running MCP, API revision, and agent-pack versions are independently observable
- `run --out` and MCP `out` preserve the requested filename for generated artifacts and sync results
- `init --apply` with an existing API key binds the checkout to that key's project instead of creating a mismatched new project

## 0.3.18 — 2026-09-11

- Native Typer `funding` status (no Click Option mix-in); pin `typer<0.26`
- Empty MCP catalog browse uses `GET /v1/capabilities?view=summary`
- Receipt printers lead with `pricing.charge.customerCharge` (customer owed)
- App presentation stays `mount_requested` until the host acknowledges mount
- Default `mcp bind` no longer rewrites user-level Cursor MCP files

## 0.3.17 — 2026-09-11

- MCP status no longer NameErrors on `AGENT_PACK_VERSION`
- Invalid registrar TLDs return `UnsupportedTld` instead of a retryable registrar outage
- Rejected checkout credentials recover by minting a new key or restarting bootstrap instead of reusing a dead `secrets.json`
- Empty public catalogs fail closed as `CatalogUnavailable`
- Stale or PID-reused stdio MCP leases are detected instead of reporting a live workspace

## 0.3.16 — 2026-09-10

- Public client identity advances past the 0.3.15 PyPI cut so post-release receipt, sentinel, and discovery fixes are no longer labeled as an already-published version
- Receipts distinguish retail `price` from owed `customerCharge` and actual `customerDebit`; Hydracept-covered executions report `$0` owed
- Capability resolve accepts natural paraphrases for transparent icons/sprites instead of overfitting to a single PNG phrase
- Transient 5xx responses and MCP tool errors carry `retryable`, `nextAction`, and `retryAfterSeconds`

## 0.3.15 — 2026-09-09

- `run --input-file` accepts PowerShell UTF-8 BOM and UTF-16 JSON files
- `capabilities describe` keeps quote metadata and includes `nextAction.exampleInput` so a request.json can be built without reverse-engineering
- `quote`, `estimate`, `invoke`, and `jobs submit` accept `--input-file`

## 0.3.14 — 2026-09-09

- Consumer-truth projection: workspace verification capabilities, doctor/checkout authority, and funding provenance no longer masquerade as entitlement or trial balances
- Capability resolve attaches retail pricing only when the descriptor has a complete retail contract; domain quote metadata no longer crashes discovery
- `hydracept run --body` / `--input-file` reads structured JSON on Windows/PowerShell without inline quoting
- Python client remains the 0.3.14 surface of this release (TypeScript/dotnet stay 0.3.5)

## 0.3.13 — 2026-09-09

- `funding status` and `doctor --json` now distinguish customer-visible managed credit, the active trial bucket, and execution-available funding (including operator grants)
- Customer-visible `$0` is no longer labeled aggregate/trial credit, and trial remaining is no longer aliased to the customer balance
- Python client remains the 0.3.13 surface of this release (TypeScript/dotnet stay 0.3.5)

## 0.3.12 — 2026-09-08

- Consumer-contract convergence: missing receipt funding evidence no longer displays as managed trial or BYOK
- Smoke wait and funding projection are evidence-based; unknown stays unknown
- Python client remains the 0.3.12 surface of this release (TypeScript/dotnet stay 0.3.5)

## 0.3.11 — 2026-09-08

- Expired `~/.hydracept/session.json` no longer blocks `gh`/`gcloud` init; init discards it and completes from local identity
- A unique folder name creates the project in the home/last-used organization when several orgs exist, instead of opening a browser

## 0.3.10 — 2026-09-07

- `init` completes from an existing `gh` or `gcloud` user login without a browser when the project choice is unambiguous
- GitHub detection reads `gh api user` JSON instead of `--jq`, and retries local identity on reused bootstrap sessions
- Connect panel auto-opens the activation URL and polls until ready; the connect page auto-submits when org + suggested name are known
- Skip asking for a project name when the folder name is already known

## 0.3.9 — 2026-09-04

- Public wheel no longer imports private `hydracept_contracts`; the MCP surface catalog is vendored in the client
- Unattended `init --apply --yes --json` binds or creates when local context is unambiguous; browser `project.connect` only when it is not
- Corrupt `.hydracept/project.json` returns `corrupt_local_binding` instead of being overwritten and auto-created
- Empty org catalogs no longer treat a local `projectId` as inaccessible
- Unique project-name match does not bind a project in the wrong GitHub org
- `present_and_yield` App lifecycle: present `ui://hydracept/app.html` and stop the turn

## 0.3.8 — 2026-09-03

- MCP interaction panel: complete seven-surface contract (connect, launch, connection, preflight, progress, review, promote)
- Fix job progress cancel/receipt/refresh, terminal states, secret-field handling, quoted preflight cost, and image terminal routing
- `hydracept_interaction_surface` hydrates full contracts on poll, run, and submit
- `image.edit.v1` OpenAI images.edit capability; native transparent output for gpt-image-2 edit and sheets
- Downstream provider prompt limits published instead of Hydracept schema caps

## 0.3.7 — 2026-09-02

- Hydracept MCP App panel (`ui://hydracept/app.html`) with seven semantic surfaces over one App
- `hydracept_interaction_surface` remounts the panel; form elicitation remains the fallback

## 0.3.5 — prior public cut

See PyPI release history for earlier notes.
