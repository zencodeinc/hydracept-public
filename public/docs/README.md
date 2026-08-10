# Quick Start

<!-- docs:marker:quick-start -->

Hydracept runs AI workloads for games—text, images, audio, and cloud models—through one API.

Free for individual developers. Bring your own provider keys. No inference markup.

A Zencode product · © Zencode Consulting Inc.

## 5-minute path

Follow [5-minute game asset](./five-minute-game-asset/) for activate → BYOK → `image.generate.v1` → receipt.

## Activate

Pick one:

1. **Browser:** open [https://hydracept.com/start](https://hydracept.com/start), complete OAuth, and save your API key and project ids.
2. **CLI:** install the package, run device login, then init (see below).

Public API: `https://api.hydracept.com`  
Configuration directory (CLI): `.hydracept/`  
Environment variables: `HYDRACEPT_API_URL`, `HYDRACEPT_API_KEY`, `HYDRACEPT_PROJECT`, `HYDRACEPT_ENVIRONMENT`

**BYOK:** Hydracept API keys authenticate callers. Provider keys (OpenAI, ElevenLabs, …) pay for inference and must be connected separately — see [Connections / BYOK](./connections/).

<!-- docs:if packages.cli.releasePublished -->
## CLI

```bash
pip install hydracept

# Prefer the module form if `hydracept` is not on PATH (common on Windows):
python -m hydracept login
python -m hydracept init --apply --yes
python -m hydracept doctor
python -m hydracept agent-context
```

`login` opens `https://api.hydracept.com/device`. Sign in, enter the terminal code, approve, then return to the terminal.

Equivalent console script (when Scripts/bin is on PATH):

```bash
hydracept login
hydracept init --apply --yes
hydracept doctor
```
<!-- docs:endif -->

<!-- docs:if packages.typescript.registryPublished|packages.python.registryPublished|packages.csharp.registryPublished -->
## Install SDKs

<!-- docs:if packages.typescript.registryPublished -->
```bash
npm install @hydracept/sdk
```
<!-- docs:endif -->

<!-- docs:if packages.csharp.registryPublished -->
```bash
dotnet add package Hydracept.Client
```
<!-- docs:endif -->

<!-- docs:if packages.python.registryPublished -->
```bash
pip install hydracept
python -m hydracept --help
```
<!-- docs:endif -->
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

Launch capabilities:

<!-- docs:launch-capabilities -->

See [Capabilities](./capabilities/) for how capability keys work.

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

See [Durable Jobs & Receipts](./jobs/) for artifacts and outputs.

## Next

- [5-minute game asset](./five-minute-game-asset/)
- [Authentication & Activation](./authentication/)
- [Connections / BYOK](./connections/)
- [Errors](./errors/)
- [Rate limits & quotas](./rate-limits/)
- [Coding Agents](./agents/)
- [Consumer Boundary](./consumer-boundary/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
