# Authentication & Activation

Hydracept has two kinds of credentials: who you are (Hydracept identity) and who pays for inference (provider keys). Keep them separate.

## Human login

Humans can activate in the browser or through CLI device authorization.

### Browser

1. Visit [https://hydracept.com/start](https://hydracept.com/start)
2. Sign in with OAuth or create an account
3. Save the one-time API key shown on the completion page

### CLI device login

```bash
pip install hydracept
python -m hydracept login
```

1. The CLI calls `POST /v1/auth/device/start` and prints a user code
2. Your browser opens `https://api.hydracept.com/device`
3. Sign in (GitHub/Google), enter the code, approve
4. The CLI polls `POST /v1/auth/device/token` and writes `.hydracept/secrets.json`
5. Run `python -m hydracept init --apply --yes` for a machine credential + project config

If the `hydracept` console script is not on your PATH (common after `pip install --user` on Windows), use `python -m hydracept …`.

Browser sessions are for Studio, device approval, and operator work. Game runtimes and CI should use machine credentials, not cookies.

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
| `HYDRACEPT_API_KEY` | Machine credential |
| `HYDRACEPT_PROJECT` | Project id |
| `HYDRACEPT_ENVIRONMENT` | Environment name |

Do not ship Hydracept API keys in game clients. For player-facing apps, call Hydracept from your server.

<!-- docs:if packages.cli.releasePublished -->
CLI helpers:

```bash
python -m hydracept login
python -m hydracept init --apply --yes
python -m hydracept doctor
```
<!-- docs:endif -->

## Provider / BYOK connection

Provider credentials (OpenAI, ElevenLabs, and others) are **not** Hydracept identity.

Hydracept stores them encrypted, validates them, and binds them to projects/environments so execution can resolve BYOK keys at runtime. See [Connections / BYOK](../connections/).

| Concern | Owned by |
|---------|----------|
| Who is calling Hydracept | Hydracept human session or API key |
| Which model account pays for inference | Customer provider credential (BYOK) |

Without a bound provider credential, durable jobs that need cloud inference will fail provider readiness — connect BYOK before your first image/audio job. The [5-minute game asset](../five-minute-game-asset/) tutorial walks through this end to end.

## Verify

`python -m hydracept doctor` (or `hydracept doctor`) runs integration checks:

- API health (`GET /healthz`)
- Authenticated diagnostics (`GET /v1/diagnostics/session`, `GET /v1/session/context`)
- Local `.hydracept/config.json` alignment with server project/environment
- Provider readiness (`GET /v1/diagnostics/providers`) for launch smoke capabilities
- Public capability list includes the launch smoke key (default `image.generate.v1`)

Exit code is non-zero when a fatal check fails. Use `--json` for CI output.

```http
GET /v1/diagnostics/session
Authorization: Bearer <HYDRACEPT_API_KEY>
```

For agent discovery without hardcoding internals: `GET /v1/agent-context`.
