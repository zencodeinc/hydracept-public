# 5-minute game asset

Generate your first game asset through Hydracept in about five minutes.

**For a free test:** Run `python -m hydracept smoke` to verify your setup. For ongoing production use, connect your own OpenAI, ElevenLabs, or Meshy key; Hydracept adds no inference markup.

## 1. Activate

### Option A — Browser (fastest)

1. Open [https://hydracept.com/start](https://hydracept.com/start)
2. Sign in with GitHub or Google
3. Save the printed API key — click **Copy setup for coding agent** if an agent will continue

### Option B — CLI (humans)

```bash
pip install -U hydracept
python -m hydracept init --apply --yes --wait
```

Sign in on the connect page, choose workspace and project, then approve. Use **Use a different account** if you have multiple GitHub or Google logins.

### Option C — Agents / headless (API key paste)

```bash
pip install -U hydracept
python -m hydracept quickstart --token "$HYDRACEPT_API_KEY" --json --smoke
```

Legacy path (still supported): `login --token` → `init --apply --yes` → `doctor` → `smoke`.  
Browser connect without API key: `init --apply --yes --json` → human opens connect URL → `init --apply --yes --json --wait`.

## 2. Verify

```bash
python -m hydracept doctor
```

Doctor prints **Next** actions when something is missing (PATH tip, BYOK URL, smoke command).

## 3. First image (smoke test or BYOK)

```bash
python -m hydracept smoke
```

Or submit manually:

```bash
export HYDRACEPT_API_URL=https://api.hydracept.com
# keys from activation / .hydracept/local.env
JOB_JSON=$(curl -sS -X POST \
  -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"context\": {
      \"productId\": \"demo-game\",
      \"projectId\": \"$HYDRACEPT_PROJECT\",
      \"environment\": \"$HYDRACEPT_ENVIRONMENT\"
    },
    \"input\": { \"prompt\": \"cute slime enemy icon, flat game art\" },
    \"execution\": { \"executionPreference\": \"automatic\" },
    \"idempotencyKey\": \"five-minute-slime-1\"
  }" \
  "$HYDRACEPT_API_URL/v1/capabilities/image.generate.v1/jobs")
```

## 4. Connect BYOK (recommended for production)

Open the BYOK form from activation (**Configure BYOK**), or visit:

`https://api.hydracept.com/v1/onboarding/byok?organizationId=…&projectId=…&environment=development`

Paste an OpenAI, ElevenLabs, or Meshy key — Hydracept encrypts and binds it. See [Connections / BYOK](../connections/).

## What you have now

- Your Hydracept workspace is authenticated
- Your first game asset job has run successfully
- Your provider billing stays on your account through BYOK

## Next

- [Quick Start](../)
- [Authentication](../authentication/)
- [Connections / BYOK](../connections/)
- [Jobs](../jobs/)
- [Agent context](https://api.hydracept.com/v1/agent-context)
