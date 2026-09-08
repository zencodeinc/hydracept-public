# Changelog

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
