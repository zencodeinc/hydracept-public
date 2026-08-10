# hydracept

Python client and CLI for the Hydracept public API — **one API for AI workloads in games**.

Free for individual developers. BYOK. No inference markup.

```bash
pip install hydracept
```

## Activate (CLI)

```bash
python -m hydracept login
python -m hydracept init --apply --yes
python -m hydracept doctor
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

Activate at https://hydracept.com/start · Docs: https://docs.hydracept.com

A Zencode product · © Zencode Consulting Inc.
