# Quick Start

<!-- Maintained for docs.hydracept.com. GitHub front door: /README.md at repo root. -->

<!-- docs:marker:quick-start -->

Hydracept is an execution control plane for software and agents that need external capabilities. Games and media are important examples.

Discovery, quoting, durable jobs, artifacts, receipts, and recoverable project history. BYOK is free; managed inference adds a 6% service fee. Eligible durable text jobs use deferred processing at 50% of standard token rates.

## 5-minute path

For one asset: `python -m hydracept run image.generate.v1 --prompt "..." --json` (composes init). For a full walkthrough, see [5-minute game asset](./five-minute-game-asset/). One-off tasks are supported — a single capability call does not require an integration commitment.

## Activate

Pick one:

1. **CLI bootstrap (recommended):** `pip install -U hydracept` then `python -m hydracept init --apply --yes --json`. Init infers the current git/workspace project when you are already signed in. Browser project selection is only required when that inference is ambiguous.
2. **Studio (browser):** [app.hydracept.com/login](https://app.hydracept.com/login) — sign in with GitHub or Google, complete onboarding, then generate in Studio. Manage plans at [Studio Billing](https://app.hydracept.com/studio/billing).
3. **Agents / headless:** `python -m hydracept init --apply --yes --json` (or use an existing key out of band with `HYDRACEPT_API_KEY`).

For coding agents, `interaction_required` is a hard human boundary. If `presentation.agentAction` is `present_and_yield` and stdio MCP exposes `hydracept_interaction_surface`, invoke that surface once with the supplied context and stop the turn. Otherwise present `action.url` verbatim. In either case, stop until the human completes activation; only then run `afterCompletion.command` / `--wait`.

See [Authentication](./authentication/) for workspace files (`.hydracept/project.json`, secrets, lazy BYOK) and CI mode (`init --apply --yes --json --ci`).

Public API: `https://api.hydracept.com`  
Configuration directory (CLI): `.hydracept/`  
Environment variables: `HYDRACEPT_API_URL`, `HYDRACEPT_API_KEY`, `HYDRACEPT_PROJECT`, `HYDRACEPT_ENVIRONMENT`

**BYOK:** Your Hydracept API key authenticates your application, while your provider key pays for inference. Run `python -m hydracept smoke` (trial budget or BYOK — a real image job) before connecting BYOK — see [Connections / BYOK](./connections/) and [Billing & plans](./billing/).

<!-- docs:if packages.cli.releasePublished -->
## CLI

```bash
pip install -U hydracept

# Prefer the module form if `hydracept` is not on PATH (common on Windows):
python -m hydracept init                              # human — opens connect URL when needed
python -m hydracept init --apply --yes --json         # agents
python -m hydracept init --apply --yes --json --ci    # CI (setup grants)
python -m hydracept doctor
python -m hydracept smoke
python -m hydracept verify
python -m hydracept agent-context
```

`configure` and `quickstart` are deprecated aliases for `init`. Device login (`python -m hydracept login`) still works for advanced flows.
<!-- docs:endif -->

## SDKs

The Python SDK and CLI are available now:

```bash
pip install -U hydracept
python -m hydracept --help
```

The TypeScript SDK is also available:

```bash
npm install @hydracept/sdk
```

<!-- docs:if packages.csharp.registryPublished -->
## .NET SDK

```bash
dotnet add package Hydracept.Client
```
<!-- docs:endif -->

<!-- docs:if !packages.typescript.registryPublished&!packages.python.registryPublished&!packages.csharp.registryPublished -->
## HTTP-first integration

Registry packages are still rolling out. Until yours is available, use the public HTTP API and [OpenAPI](https://hydracept.com/openapi/hydracept-v1.json). The curl flow below is the supported clean-room path.
<!-- docs:endif -->

## Discover capabilities

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/capabilities
```

The live catalog is `GET /v1/capabilities` (or `python -m hydracept agent-context`). Do not freeze a launch-key list from this README.

See [Capabilities](./capabilities/) for how capability keys work.

For image production (Sheet & Slice, transparent output, variants), see [Image production](./image-production/).

For Unity 6 Editor integration (generate, sheet slice, import with provenance), see [Unity integration](./unity-integration/).

## Submit a durable job

```bash
JOB_JSON=$(curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "productId": "my-product",
      "projectId": "cpr_...",
      "environment": "development"
    },
    "input": { "prompt": "cute slime icon" },
    "execution": { "executionPreference": "automatic" },
    "idempotencyKey": "demo-1"
  }' \
  https://api.hydracept.com/v1/capabilities/image.generate.v1/jobs)

echo "$JOB_JSON"
JOB_ID=$(printf '%s' "$JOB_JSON" | python -c "import sys,json; print(json.load(sys.stdin)['jobId'])")
```

The submit response is a `HydraceptJob` object. Use `jobId` from that payload for poll and receipt calls.

## Poll the job

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/jobs/$JOB_ID
```

Poll until status is `succeeded`, `failed`, or `canceled`.

## Fetch the receipt

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/jobs/$JOB_ID/receipt
```

## Find and inspect later

If an agent no longer has the ID—or a user simply says “the last job failed”—query project history instead of asking the human to find it:

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  "https://api.hydracept.com/v1/projects/cpr_.../jobs?outcome=failed&limit=10"
```

The list is prompt-free. Once the relevant job is identified, intentionally inspect only that job with `GET /v1/jobs/{jobId}`. MCP provides the shorter agent loop:

```text
hydracept_jobs_find(intent="failed")
→ hydracept_job_inspect(job_id)
```

For prior successful outputs use `intent="reusable"`; Hydracept highlights an explicitly selected artifact when one exists. A retry always uses a new idempotency key.

See [Durable Jobs & Receipts](./jobs/) for filters, artifacts, inspection, and outputs.

## Next

- [5-minute game asset](./five-minute-game-asset/)
- [Authentication & Activation](./authentication/)
- [Durable Jobs & Receipts](./jobs/)
- [Pinned Execution](./pinned-execution/)
- [Execution provenance](./provenance/)
- [Research Inference Protocol](./research/)
- [Billing & plans](./billing/)
- [Deferred processing](./deferred-processing/)
- [Connections / BYOK](./connections/)
- [Errors](./errors/)
- [Rate limits & quotas](./rate-limits/)
- [Coding Agents](./agents/)
- Plugin homepage: [https://hydracept.com/plugin](https://hydracept.com/plugin)
- [Capability requests](./capability-requests/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
