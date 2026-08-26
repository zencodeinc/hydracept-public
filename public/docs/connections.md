# Connections / BYOK

Connect your own provider keys and keep the provider relationship on your account. Hydracept encrypts credentials and uses them only for the project and environment you authorize. You pay the provider directly; Hydracept adds no inference markup.

Hydracept API keys identify callers. Provider credentials pay for model inference. See [Authentication & Activation](../authentication/) for how those fit together.

## Interactive BYOK (recommended)

After activation, open **Configure BYOK** on the completion page (or `/v1/onboarding/byok?organizationId=…&projectId=…`). Paste an OpenAI, ElevenLabs, or Meshy key — Hydracept encrypts and binds it in one step.

New Free workspaces include one free test run so `python -m hydracept smoke` can verify your setup before you connect a provider. Ongoing generation uses your own provider keys.

## Manual provider connection (API)

Connect providers through the organization-scoped public API:

1. **Create** — `POST /v1/organizations/{orgId}/provider-credentials` stores the provider secret. Hydracept encrypts it at rest and validates the credential as part of create (there is no separate public validate route).
2. **Bind** — `POST /v1/organizations/{orgId}/provider-credentials/{credentialId}/bindings` attaches the credential to the project/environment that may use it at execution time.

```http
POST /v1/organizations/{orgId}/provider-credentials
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

```http
POST /v1/organizations/{orgId}/provider-credentials/{credentialId}/bindings
Authorization: Bearer <HYDRACEPT_API_KEY>
Content-Type: application/json
```

Use the activation form, Studio, or the API with your Hydracept machine credential. Keep provider secrets off game clients.

Walkthrough: [5-minute game asset](../five-minute-game-asset/).

<!-- docs:if provider_bootstrap.production_verified -->
## Automated bootstrap

Automated provider setup supports provisioning, validation, binding, and rotation for eligible providers.
<!-- docs:endif -->

<!-- docs:if !provider_bootstrap.production_verified -->
## Automated bootstrap

If automated setup is unavailable for your provider, connect credentials with the create → bind flow above.
<!-- docs:endif -->

<!-- docs:if inference_sources.local_inference -->
## Local inference

Local and private inference endpoints are available as an execution source for eligible capabilities.
<!-- docs:endif -->

## Next

- [Capabilities](../capabilities/)
- [Durable Jobs & Receipts](../jobs/)
- [Errors](../errors/)
