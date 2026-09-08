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

See [Quick Start](../) and [Durable jobs](../jobs/).

## Current release (0.3.12)

`pip install -U hydracept` installs the current PyPI cut. Receipts copy funding from admission evidence; missing evidence stays `unknown` and is never displayed as BYOK or managed trial. Domain and CPU capabilities omit inference `billingModes`.

## MCP interaction panel (0.3.9+)

Stdio MCP (`python -m hydracept mcp serve`) ships one Hydracept App at `ui://hydracept/app.html` with seven semantic surfaces: `project.connect`, `capability.launch`, `connection.resolve`, `authorization.preflight`, `job.progress`, `artifact.review`, and `change.promote`. Use `hydracept_interaction_surface` when a human decision or structured input is required. Unattended `init --apply --yes --json` binds or creates when unambiguous. Upgrade with `pip install -U hydracept` (0.3.12+ required for init to reuse `gh`/`gcloud` without a browser).
