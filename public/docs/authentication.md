# Authentication & Activation

Hydracept has two kinds of credentials: who you are (Hydracept identity) and who pays for inference (provider keys). Keep them separate.

## Human login

Humans can activate in the browser or through the CLI connect flow.

### Studio (recommended for creators)

1. Visit [https://app.hydracept.com/login](https://app.hydracept.com/login)
2. Sign in with GitHub or Google
3. Complete onboarding (project name and use case)
4. Generate in Studio; connect BYOK under **Connections**; upgrade under **Billing**

If you use multiple GitHub or Google accounts, pick the account that owns your Hydracept workspace when signing in.

### Browser API activation

1. Visit [https://hydracept.com/start](https://hydracept.com/start)
2. Sign in with GitHub or Google
3. Save the one-time API key shown on the completion page

### CLI connect flow (recommended for local projects)

```bash
pip install -U hydracept
python -m hydracept init --apply --yes --wait
```

1. The CLI opens a connect URL (or prints it when using `--json`)
2. Sign in with GitHub or Google on the connect page
3. Choose workspace, project, and environment — confirm the summary matches your intent
4. Approve setup; the CLI continues automatically when `--wait` is set

If you use multiple sign-in accounts, use **Use a different account** on the connect page before approving.

Agent / scripted flow:

```bash
python -m hydracept init --apply --yes --json
# present interaction_required.action.url to the human
python -m hydracept init --apply --yes --json --wait
```

The CLI reuses `.hydracept/bootstrap-session.json` so repeated runs poll the same connect session.

### CLI device login

```bash
python -m hydracept login
```

1. The CLI calls `POST /v1/auth/device/start` and prints a user code
2. Your browser opens `https://api.hydracept.com/device`
3. Sign in (GitHub/Google), enter the code, approve
4. The CLI polls `POST /v1/auth/device/token` and stores a human session in `~/.hydracept/session.json`
5. Run `python -m hydracept init --apply --yes` to bind the project and create an installation API key

### Agent / headless login (API key)

Preferred unattended path:

```bash
export HYDRACEPT_API_KEY=...
python -m hydracept init --apply --yes --json
```

Or CI:

```bash
python -m hydracept init --apply --yes --ci --json
```

Legacy path:

```bash
python -m hydracept login --token "$HYDRACEPT_API_KEY"
python -m hydracept init --apply --yes
python -m hydracept doctor
python -m hydracept smoke
```

If the `hydracept` console script is not on your PATH (common after `pip install --user` on Windows), use `python -m hydracept …`.

Browser sessions are for Studio and connect/device approval. Game runtimes and CI should use API keys, not browser cookies.

## Project and environment provisioning

Onboarding creates:

- an organization
- a project (`projectId`, often `cpr_…`)
- an environment (for example `development`)

Every capability job needs that context:

```json
{
  "context": {
    "productId": "my-product",
    "projectId": "cpr_...",
    "environment": "development"
  }
}
```

## Machine / service credential

Machine callers use a Hydracept API key as a bearer token:

```http
Authorization: Bearer <HYDRACEPT_API_KEY>
```

Recommended environment variables:

| Variable | Purpose |
|----------|---------|
| `HYDRACEPT_API_URL` | API base (`https://api.hydracept.com`) |
| `HYDRACEPT_API_KEY` | Your API key |
| `HYDRACEPT_PROJECT` | Project id |
| `HYDRACEPT_ENVIRONMENT` | Environment name |

Do not ship Hydracept API keys in game clients. For player-facing apps, call Hydracept from your server.

<!-- docs:if packages.cli.releasePublished -->
CLI helpers:

```bash
python -m hydracept init --apply --yes --wait
python -m hydracept doctor
python -m hydracept smoke
```
<!-- docs:endif -->

## Provider / BYOK connection

Provider credentials (OpenAI, ElevenLabs, and others) are separate from your Hydracept login.

Hydracept stores them encrypted, validates them, and binds them to projects/environments so execution can resolve BYOK keys at runtime. See [Connections / BYOK](../connections/).

| Concern | Owned by |
|---------|----------|
| Who is calling Hydracept | Hydracept human session or API key |
| Which model account pays for inference | Customer provider credential (BYOK) |

Before connecting BYOK, run `python -m hydracept smoke` once to verify your setup. Then connect a provider for production jobs. The [5-minute game asset](../five-minute-game-asset/) tutorial walks through this end to end.

## Verify

`python -m hydracept doctor` (or `hydracept doctor`) runs integration checks and prints **Next** actions on failure:

- API health (`GET /healthz`)
- Authenticated diagnostics (`GET /v1/diagnostics/session`, `GET /v1/session/context`)
- Local `.hydracept/config.json` alignment with server project/environment
- Provider readiness and test-run status (`GET /v1/diagnostics/providers`)
- Public capability list includes the smoke capability (default `image.generate.v1`)

Exit code is non-zero when a fatal check fails. Use `--json` for CI output.

```http
GET /v1/diagnostics/session
Authorization: Bearer <HYDRACEPT_API_KEY>
```

For agent discovery without hardcoding internals: `GET /v1/agent-context`.
