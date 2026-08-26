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
