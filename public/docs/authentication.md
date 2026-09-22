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
python -m hydracept init --apply --yes --json
```

Hydracept first checks whether the workspace already has a valid Hydracept login. If not, it can use an already-authenticated GitHub CLI (`gh`) or Google Cloud CLI (`gcloud`) user account to establish identity automatically.

If GitHub CLI is already authenticated, Hydracept may reuse the active `github.com` identity for local activation. If `gcloud` is already authenticated as a human user account, Hydracept may reuse that Google identity. Provider/API credentials are not read from GitHub or Google Cloud and remain separate. `gh` has one active `github.com` account at a time; `gcloud` has one active user account. Change them with `gh auth switch` / `gcloud config set account` before `python -m hydracept init`.

When both CLIs are logged in, Hydracept tries GitHub first, then Google. Browser OAuth is not required merely because two supported developer logins exist.

The foreign credential is handled only inside the Hydracept CLI process and sent to the pinned first-party Hydracept identity endpoint for server-side verification. `HYDRACEPT_APP_URL` cannot redirect that credential. It is not exposed to the coding agent, MCP panel, project files, or normal command output, and Hydracept does not change your GitHub or Google login state.

The resulting Hydracept human session is kept process-local until the existing bootstrap completion authority succeeds. It is never sent to a custom `HYDRACEPT_API_URL`; custom/local/staging origins use explicit authentication instead.

When there is a usable `gh` or `gcloud` user login, ordinary production setup can therefore continue without opening a browser. A leftover expired `~/.hydracept/session.json` is discarded so it cannot skip that path. Hydracept then infers the current project from the workspace and git repository (folder name, git root, and GitHub remote) and defaults a new workspace to `development`. If several organizations exist, a unique folder name is created in the home/last-used organization. Browser project selection is a fallback for genuine ambiguity — not a mandatory step on the normal path.

If automatic identity is unavailable or the account/project choice is ambiguous, `init` returns the existing `interaction_required.action.url`. The JSON includes `identity` and `projectResolution` so agents can tell a signed-in user apart from a failed login. Open that exact URL and finish the choice in the browser; the pending bootstrap session is reused.

Typical unattended result:

1. Identity is already authenticated (GitHub CLI / Google Cloud CLI / Hydracept session)
2. The workspace maps to one existing project, or Hydracept creates that project in `development`
3. Init writes `.hydracept/project.json`, installs the workspace API key, and configures MCP
4. Status is `ready`, with `project.resolution` describing how the project was chosen

Browser interaction is required only when:

- you are not signed in yet and neither `gh` nor `gcloud` is logged in
- several existing projects match the same repository
- several organizations are equally plausible and there is no home/last-used organization
- the inferred project is inaccessible
- you are rebinding in a way that needs confirmation

To change the automatic binding later:

```bash
python -m hydracept project use <project-id-or-name>
python -m hydracept init --apply --yes --json --project <project-id-or-name>
```

Agent / scripted flow:

```bash
python -m hydracept init --apply --yes --json
# If status is interaction_required, present action.url to the human.
python -m hydracept init --apply --yes --json --wait
```

The CLI reuses `.hydracept/bootstrap-session.json` so repeated runs and panel polls keep the same connect session. If `gh` or `gcloud` is logged in, those retries can complete local identity instead of opening a browser.

CI is deliberately different: `init --ci` never inspects local human GitHub or Google CLI sessions and requires explicit machine credentials.

### CLI device login

```bash
python -m hydracept login
```

Device login remains available when you explicitly want a reusable Hydracept human session before entering a project:

1. The CLI calls `POST /v1/auth/device/start` and prints a user code
2. Your browser opens the Hydracept device page
3. Sign in (GitHub/Google), enter the code, approve
4. The CLI stores a human session in `~/.hydracept/session.json`
5. Run `python -m hydracept init --apply --yes` to bind the project and create an installation API key

### Agent / headless login (API key)

Preferred unattended machine path:

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

Browser sessions are for Studio and human account authority. Project runtimes and CI should use API keys, not browser cookies.

## Identity authority

Automatic local sign-in does not turn a GitHub credential into a Hydracept execution credential.

The authority chain remains:

```text
verified developer identity
→ Hydracept human session
→ bootstrap completion
→ project installation API key
→ capability execution
```

The local identity assertion itself does not mint an installation key, setup grant, provider connection, or payment authorization. Those remain separate Hydracept authorities.

GitHub Enterprise Hosted / GHES logins, service-account identities, and `gcloud` impersonation are not part of the automatic path. Browser login remains the fallback.

## Project and environment provisioning

Onboarding creates or resolves:

- an organization
- a repository project (`projectId`, often `cpr_…`)
- an environment (normally `development` for a new local project)

`init` prefers an existing `.hydracept/project.json` binding. If that file is missing, it matches the current git repository or workspace name to a project you already own, or creates one. The default environment is `development`.

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

## Managed trial and funding

Authentication and Hydracept-funded inference are separate decisions. Proving a developer identity may connect the workspace even when managed-trial allowance is reduced or exhausted.

When managed first-use allowance is unavailable, the capability is still ready — connect BYOK or fund managed execution. See [Billing & plans](../billing/) and [Capabilities](../capabilities/).

## Verify

`python -m hydracept doctor` (or `hydracept doctor`) runs integration checks and prints **Next** actions on failure:

- API health (`GET /healthz`)
- Authenticated diagnostics (`GET /v1/diagnostics/session`, `GET /v1/session/context`)
- Local workspace alignment with server project/environment
- Provider readiness and test-run status (`GET /v1/diagnostics/providers`)
- Public capability list includes the smoke capability (default `image.generate.v1`)

Exit code is non-zero when a fatal check fails. Use `--json` for CI output.

```http
GET /v1/diagnostics/session
Authorization: Bearer <HYDRACEPT_API_KEY>
```

For agent discovery without hardcoding internals: `GET /v1/agent-context`.
