# hydracept

mcp-name: com.hydracept/hydracept

Python client for the Hydracept public API — an execution control plane for software and agents that need external capabilities.

```bash
pip install hydracept
```

Required onboarding is `python -m hydracept init --apply --yes --json`. Init reuses an authenticated GitHub CLI (`gh`) session when one is already available; otherwise use a browser connect flow or `HYDRACEPT_API_KEY`. Canonical docs are https://docs.hydracept.com. `hydracept run --input-file` accepts structured JSON on Windows/PowerShell, including UTF-8 BOM and UTF-16 files. Funding status reports customer-visible managed credit separately from trial and operator execution funding. Receipts distinguish retail price from the amount the customer actually owes or was debited (`pricing.customerCharge`). Domain and CPU capabilities omit inference `billingModes`.

```bash
python -m hydracept init --apply --yes --json
python -m hydracept doctor
python -m hydracept verify
python -m hydracept pinned --help
```

Pinned Execution (RIP) and provenance:

```bash
python -m hydracept pinned run body.json
python -m hydracept pinned get <receipt_id>
python -m hydracept lockfile emit <receipt_id>
python -m hydracept verify
```

## Developer onboarding

```bash
python -m hydracept init --apply --yes --json
python -m hydracept doctor
python -m hydracept agents install --auto
python -m hydracept smoke
```

Native integrations for **Cursor**, **Claude Code**, and **Google Antigravity** ship via the Agent Pack (`agents install`). Session hooks inject local readiness only — smoke is explicit.

## Agent / CI path (secret via env, not prompt)

```bash
export HYDRACEPT_API_KEY=hydracept_...
python -m hydracept quickstart --json --smoke
python -m hydracept consumer-check --strict
```

## Breaking change in 0.2.3

`hydracept login` (device flow) stores a **human session** only. Mint a workspace API key with:

```bash
python -m hydracept keys create --configure
```

Docs: https://docs.hydracept.com · Start: https://hydracept.com/start

A Zencode company · © Zencode Consulting Inc.
