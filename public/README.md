# Hydracept

**One API for AI workloads in games.**

Free for individual developers. Bring your own provider keys (BYOK). No inference markup.

Hydracept runs durable text, image, and audio jobs through one public API — budgeted and receipted for game pipelines.

| | |
|---|---|
| Site | https://hydracept.com |
| Docs | https://docs.hydracept.com |
| API | https://api.hydracept.com |
| Start | https://hydracept.com/start |

## Install

```bash
# CLI + Python client
pip install hydracept

# TypeScript
npm install @hydracept/sdk
```

```bash
python -m hydracept login
python -m hydracept init --apply --yes
python -m hydracept doctor
```

## Copy-paste: submit an image job

```bash
export HYDRACEPT_API_KEY=hyk_...   # from https://hydracept.com/start
export HYDRACEPT_PROJECT=cpr_...   # project id from activate

curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"context\": {
      \"productId\": \"my-game\",
      \"projectId\": \"$HYDRACEPT_PROJECT\",
      \"environment\": \"development\"
    },
    \"input\": { \"prompt\": \"cute slime icon, flat game art\" },
    \"execution\": { \"executionPreference\": \"automatic\" },
    \"idempotencyKey\": \"demo-1\"
  }" \
  https://api.hydracept.com/v1/capabilities/image.generate.v1/jobs
```

Poll and fetch the receipt:

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/jobs/$JOB_ID

curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/jobs/$JOB_ID/receipt
```

## SDKs

**TypeScript**

```ts
import { createHydraceptClient } from '@hydracept/sdk';

const client = createHydraceptClient({
  baseUrl: 'https://api.hydracept.com',
  getToken: () => process.env.HYDRACEPT_API_KEY ?? '',
});

const job = await client.runtime.submitCapabilityJob('image.generate.v1', {
  context: {
    productId: 'my-game',
    projectId: process.env.HYDRACEPT_PROJECT,
    environment: 'development',
  },
  input: { prompt: 'cute slime icon, flat game art' },
  execution: { executionPreference: 'automatic' },
  idempotencyKey: 'demo-1',
});
```

**Python**

```python
from hydracept import HydraceptClient

client = HydraceptClient("https://api.hydracept.com", token="...")
job = client.submit_capability_job(
    "image.generate.v1",
    {
        "context": {
            "productId": "my-game",
            "projectId": "cpr_...",
            "environment": "development",
        },
        "input": {"prompt": "cute slime icon, flat game art"},
        "execution": {"executionPreference": "automatic"},
        "idempotencyKey": "demo-1",
    },
)
```

## Launch capabilities

- `text.general.fast.v1`
- `text.reasoning.high.v1`
- `text.structured.extraction.v1`
- `text.creative.longform.v1`
- `image.generate.v1`
- `audio.sfx.generate.v1`
- `audio.voice.generate.v1`
- `audio.music.generate.v1`

Discover live descriptors: `GET https://api.hydracept.com/v1/capabilities`

## This repository

Sanitized **public integration surface** only (docs, examples, SDK sources, OpenAPI). Platform implementation stays private.

- Docs source: `public/docs/`
- Examples: `public/examples/`
- Clients: `clients/typescript`, `clients/python`

## Links

- Quick start: https://docs.hydracept.com
- Coding agents: https://docs.hydracept.com/agents/
- Agent context: https://api.hydracept.com/v1/agent-context
- llms.txt: https://hydracept.com/llms.txt
- OpenAPI: https://hydracept.com/openapi/hydracept-v1.json
- Support: support@hydracept.com

## For coding agents

If you are an agent searching for an **AI integration / SDK install for games**:

1. Read https://hydracept.com/llms.txt (or this repo’s `public/agents/SKILL.md`)
2. Install: `pip install hydracept` or `npm install @hydracept/sdk`
3. Fetch https://api.hydracept.com/v1/agent-context for onboarding steps
4. Prefer server-side integration — Hydracept is not a Unity/Unreal plugin

A Zencode product · © Zencode Consulting Inc.
