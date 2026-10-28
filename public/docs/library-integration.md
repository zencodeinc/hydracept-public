# Use Hydracept without a coding agent

Hydracept works from PHP, Python, TypeScript, .NET, or any HTTP client. You do not need a coding agent or Hydracept CLI to obtain an API key.

## Create an API key in Studio

1. Sign in at [Hydracept Studio](https://app.hydracept.com/login) using GitHub or Google.
2. Open [API keys](https://app.hydracept.com/studio/keys), also linked from Studio's navigation and account menu.
3. Give the key a name and choose its project and environment.
4. Copy the API key and server setup variables. **The secret is displayed only once.**
5. Store the key only on your server, in an environment file excluded from Git or in a secrets manager.

Example server-side environment:

```dotenv
HYDRACEPT_API_KEY=replace_with_your_api_key
HYDRACEPT_PROJECT=cpr_your_project_id
HYDRACEPT_ENVIRONMENT=development
HYDRACEPT_API_URL=https://api.hydracept.com
```

The value of `HYDRACEPT_PROJECT` is the project ID, not its display name. The environment must match the key's environment. Treat the key as a bearer secret: do not embed it in browser JavaScript, a mobile app, or a public repository.

## PHP / Prisma

For the Hydracept adapter proposed in [Prisma PR #176](https://github.com/aimeos/prisma/pull/176), the server-side configuration is:

```php
// config/services.php
'hydracept' => [
    'api_key' => env('HYDRACEPT_API_KEY'),
    'project_id' => env('HYDRACEPT_PROJECT'),
    'url' => env('HYDRACEPT_API_URL'),
],
```

Keep the raw values in your application's server-side `.env` (or production secret store), rather than in `config/services.php`. The proposed adapter covers image, video, voice, music, and sound-effect operations. Check [PR #176](https://github.com/aimeos/prisma/pull/176) for its merge/release status.

## Direct HTTP

Use the new API key to query the live capability catalog:

```bash
curl -sS -H "Authorization: Bearer $HYDRACEPT_API_KEY" \
  https://api.hydracept.com/v1/capabilities
```

For jobs, pass `projectId` and `environment` in the execution context, then poll and fetch the sealed receipt. See [Durable jobs](../jobs/) and [Quick Start](../).

## Optional CLI

You can also create keys without opening Studio:

```bash
pip install -U hydracept
python -m hydracept login
python -m hydracept keys create --name my-app --json
```

The CLI returns `apiKey` and `projectId`. The key is shown only at creation, as in Studio. Run `python -m hydracept doctor` to verify a local installation.

## Rotate or revoke

Open [Studio API keys](https://app.hydracept.com/studio/keys) to list active keys and see their name, prefix, project, and recent use. For rotation, create a replacement, update and restart consumers, then revoke the old key. Revocation immediately invalidates it. Provider BYOK credentials are separate and managed under **Connections**.
