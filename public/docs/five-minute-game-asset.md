# 5-minute game asset

Generate a game-ready image through Hydracept in about five minutes. This path uses a durable job (`image.generate.v1`) so retries, polling, and receipts work the same way in CI as they do locally.

**Bring your own key (BYOK):** Hydracept does not mark up inference. You authenticate to Hydracept with an API key, then attach a provider credential (for example OpenAI) so image jobs can run. Without a bound provider credential, job submit may succeed but execution will fail provider readiness checks.

## 1. Activate

Pick one path:

### Option A — Browser (fastest first account)

1. Open [https://hydracept.com/start](https://hydracept.com/start)
2. Sign in with GitHub (or Google when enabled)
3. Save the printed `HYDRACEPT_API_KEY`, project id, and environment

### Option B — CLI device login

```bash
pip install hydracept
# Windows / PATH issues: use python -m hydracept instead of hydracept
python -m hydracept login
python -m hydracept init --apply --yes
python -m hydracept doctor
```

`login` opens `https://api.hydracept.com/device`. Sign in, enter the terminal code, approve, then return to the terminal.

## 2. Configure environment

```bash
export HYDRACEPT_API_URL=https://api.hydracept.com
export HYDRACEPT_API_KEY=hydracept_...
export HYDRACEPT_PROJECT=cpr_...
export HYDRACEPT_ENVIRONMENT=development
```

On Windows PowerShell:

```powershell
$env:HYDRACEPT_API_URL="https://api.hydracept.com"
$env:HYDRACEPT_API_KEY="hydracept_..."
$env:HYDRACEPT_PROJECT="cpr_..."
$env:HYDRACEPT_ENVIRONMENT="development"
```

## 3. Attach a provider credential (BYOK)

Hydracept identity ≠ provider billing. Create and bind a provider credential for the project/environment that will run image jobs. See [Connections / BYOK](../connections/).

Typical flow:

1. `POST /v1/organizations/{orgId}/provider-credentials` with your OpenAI (or other) secret
2. `POST .../bindings` to attach it to `HYDRACEPT_PROJECT` + `HYDRACEPT_ENVIRONMENT`
3. Confirm with `python -m hydracept doctor` (provider readiness checks)

## 4. Submit an image job

```bash
JOB_JSON=$(curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"context\": {
      \"productId\": \"demo-game\",
      \"projectId\": \"$HYDRACEPT_PROJECT\",
      \"environment\": \"$HYDRACEPT_ENVIRONMENT\"
    },
    \"input\": { \"prompt\": \"cute slime enemy icon, flat game art, transparent background\" },
    \"execution\": { \"executionPreference\": \"automatic\" },
    \"idempotencyKey\": \"five-minute-slime-1\"
  }" \
  "$HYDRACEPT_API_URL/v1/capabilities/image.generate.v1/jobs")

echo "$JOB_JSON"
JOB_ID=$(printf '%s' "$JOB_JSON" | python -c "import sys,json; print(json.load(sys.stdin)['jobId'])")
```

## 5. Poll and fetch the receipt

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  "$HYDRACEPT_API_URL/v1/jobs/$JOB_ID"

curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  "$HYDRACEPT_API_URL/v1/jobs/$JOB_ID/receipt"
```

Poll until status is `succeeded`, `failed`, or `canceled`. The receipt includes artifact download paths when generation succeeds.

## What you just proved

- Hydracept authenticated your **caller** (API key)
- Your **provider credential** paid for inference (BYOK)
- A durable capability job is the right primitive for game asset pipelines

## Next

- [Quick Start](../)
- [Authentication & Activation](../authentication/)
- [Connections / BYOK](../connections/)
- [Durable Jobs & Receipts](../jobs/)
- [Capabilities](../capabilities/)
