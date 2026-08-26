# hydracept

Python client for the Hydracept public API — production-ready game assets, with a receipt for every run.

```bash
pip install hydracept
```

```bash
python -m hydracept init
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
