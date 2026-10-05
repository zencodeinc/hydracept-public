# Python SDK

Install the public Python client and CLI:

```bash
pip install -U hydracept
python -m hydracept init --apply --yes --json
python -m hydracept doctor
python -m hydracept smoke
```

Prefer `python -m hydracept` on Windows if `hydracept.exe` is not on PATH.

Smoke uses the Free-plan trial budget or BYOK. It is a real image job, not a no-op health check.

Workspace-aware invoke:

```python
from hydracept import HydraceptWorkspace

with HydraceptWorkspace.open() as hydracept:
    result = hydracept.invoke("text.general.fast.v1", {"input": {"prompt": "hello"}})
```

See [Quick Start](../), [Migrating to 0.5.0](../migrating-0.5.0/), and [Durable jobs](../jobs/).

## Current release (0.5.1)

Production requires **`pip install -U "hydracept>=0.5.1"`**. Publish **0.5.1** to PyPI, npm, and NuGet before deploying this API revision.

`hydracept init --apply --yes` reports provider keys found locally and uploads **only** when you pass **`--adopt-keys`** (all discovered) or **`--adopt-key-providers openai,...`**. Use **`--no-adopt`** to skip uploads entirely. Older clients call HTTP routes that return **410** `LEGACY_ROUTE_REMOVED`. See [Migrating to 0.5.0](../migrating-0.5.0/).

Use `python -m hydracept run <key> --input-file request.json --json` for structured inputs (PowerShell-safe, including UTF-8 BOM and UTF-16 files). `python -m hydracept capabilities describe` includes `nextAction.exampleInput` for constructing that file. `python -m hydracept funding status --json` reports customer-visible managed credit separately from the active trial bucket and execution-available funding. Receipts copy funding from admission evidence; missing evidence stays `unknown` and is never displayed as BYOK or managed trial. Hydracept-covered executions report `$0` `customerCharge` while retail `price` remains visible. Domain and CPU capabilities omit inference `billingModes`.

## MCP interaction panel (0.5.0+)

Stdio MCP (`python -m hydracept mcp serve`) ships one Hydracept App at `ui://hydracept/app.html` with seven semantic surfaces: `project.connect`, `capability.launch`, `connection.resolve`, `authorization.preflight`, `job.progress`, `artifact.review`, and `change.promote`. Use `hydracept_interaction_surface` when a human decision or structured input is required. Unattended `init --apply --yes --json` binds or creates when unambiguous. Reload MCP after upgrading to **hydracept 0.5.0+**.
