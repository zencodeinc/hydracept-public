# hydracept

Python client and CLI for the Hydracept public API — **one API for AI workloads in games**.

Free for individual developers. BYOK. No inference markup.

```bash
pip install hydracept
```

Prefer the module entry point (works when `hydracept` is not on PATH, common on Windows):

```bash
python -m hydracept --help
python -m hydracept login --token <HYDRACEPT_API_KEY>   # agents / headless
python -m hydracept login                               # browser device flow
python -m hydracept init --apply --yes
python -m hydracept doctor
python -m hydracept smoke
```

## Copy-paste job

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
print(job["jobId"])
```

Activate at https://hydracept.com/start · Docs: https://docs.hydracept.com · 5-minute path: https://docs.hydracept.com/five-minute-game-asset/

A Zencode product · © Zencode Consulting Inc.
