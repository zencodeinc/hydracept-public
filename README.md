# Hydracept

Hydracept is an execution control plane for software and AI agents that need external capabilities—text, reasoning, image, audio, video, 3D, domains, and compute—through one API with discovery, quotes, durable jobs, artifacts, receipts, budgets, and BYOK. Games and media are common examples; a headline workflow is AI game assets from Cursor or Claude Code into Unity ([workflow overview](https://hydracept.com/agent-game-assets)).

**Pricing (summary):** Free for individual developers; BYOK at 0% Hydracept fee; managed inference is provider price + 6% service fee where enabled; eligible durable text jobs can use deferred processing at 50% of standard token rates. Details: [hydracept.com/pricing](https://hydracept.com/pricing) and [Billing docs](https://docs.hydracept.com/billing/).

## Install

| Surface | Command |
|--------|---------|
| Python CLI & SDK | `pip install -U hydracept` |
| TypeScript | `npm install @hydracept/sdk` |
| .NET | `dotnet add package Hydracept.Client` |
| Unity (UPM) | `com.hydracept.unity` — see [Unity integration](https://docs.hydracept.com/unity-integration/) |

Public HTTP API: `https://api.hydracept.com` · OpenAPI: [hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json) · Agent context: `GET https://api.hydracept.com/v1/agent-context`

## Bootstrap

```bash
pip install -U hydracept
python -m hydracept init --apply --yes --json
python -m hydracept doctor
```

Studio (browser): [app.hydracept.com/login](https://app.hydracept.com/login). For CI or headless use, set `HYDRACEPT_API_KEY` and run the same init command with `--ci` when you need setup grants. Workspace files live under `.hydracept/` — see [Authentication](https://docs.hydracept.com/authentication/).

## Minimal example

One-shot image generation (composes init when the workspace can be bootstrapped):

```bash
python -m hydracept run image.generate.v1 --prompt "transparent 1024x1024 blue slime icon" --json
```

Python SDK (after init binds the workspace):

```python
from hydracept.client import HydraceptClient

client = HydraceptClient.from_workspace()
job = client.submit_capability_job(
    "image.generate.v1",
    {
        "input": {"prompt": "cute slime icon, flat game art"},
        "execution": {"executionPreference": "automatic"},
        "idempotencyKey": "demo-1",
    },
)
finished = client.wait_for_job(job["jobId"])
receipt = client.get_job_receipt(job["jobId"])
```

Discover capabilities live (do not hard-code keys from this README):

```bash
python -m hydracept capabilities find "generate an image"
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" https://api.hydracept.com/v1/capabilities
```

More examples: [public/examples/](https://github.com/zencodeinc/hydracept-public/tree/main/public/examples).

## MCP (Cursor & Claude Code)

In a project checkout, stdio MCP is the default after init:

```bash
python -m hydracept init --apply --yes --json   # binds MCP to workspace secrets; reload MCP if prompted
python -m hydracept mcp serve                   # stdio server
python -m hydracept agents install --auto       # Cursor / Claude Code plugin + hooks
```

- **Plugin & install links:** [hydracept.com/plugin](https://hydracept.com/plugin)
- **Hosted MCP (no repo checkout):** `https://api.hydracept.com/mcp` with bearer `HYDRACEPT_API_KEY`
- **MCP Registry name:** `com.hydracept/mcp`

Do not paste workspace API keys into IDE plugin config when stdio bind is available. Full agent guide: [Coding Agents](https://docs.hydracept.com/agents/).

## Documentation

| Topic | Link |
|-------|------|
| Docs home | [docs.hydracept.com](https://docs.hydracept.com/) |
| Quick start (detailed) | [Quick Start](https://docs.hydracept.com/) |
| Capabilities & jobs | [Capabilities](https://docs.hydracept.com/capabilities/), [Jobs & receipts](https://docs.hydracept.com/jobs/) |
| Image production | [Image production](https://docs.hydracept.com/image-production/) |
| Unity | [Unity integration](https://docs.hydracept.com/unity-integration/) |
| BYOK & billing | [Connections / BYOK](https://docs.hydracept.com/connections/), [Billing](https://docs.hydracept.com/billing/) |
| LLM-oriented summary | [hydracept.com/llms.txt](https://hydracept.com/llms.txt) |
| Product manifest | [/.well-known/hydracept.json](https://hydracept.com/.well-known/hydracept.json) |

## Repository layout

- `clients/python` — PyPI package `hydracept` (CLI, SDK, local MCP)
- `clients/typescript` — npm `@hydracept/sdk`
- `clients/csharp` — NuGet `Hydracept.Client`
- `packages/unity` — Unity Editor package
- `public/docs` — source for [docs.hydracept.com](https://docs.hydracept.com/) (Quick Start content; this root README is the GitHub front door)

## License

MIT — see [LICENSE](./LICENSE). Package metadata on PyPI, npm, and NuGet also lists MIT.
