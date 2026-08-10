# Connections / BYOK

Bring your own provider keys. Hydracept encrypts credentials at rest and resolves them at execution time. You pay the provider directly—Hydracept adds no inference markup.

Hydracept API keys identify callers. Provider credentials pay for model inference. See [Authentication & Activation](../authentication/) for how those fit together.

## Manual provider connection (launch)

At initial public launch, connect providers through the organization-scoped public API:

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

Use Studio or the API with your Hydracept machine credential. Keep provider secrets off game clients.

Walkthrough: [5-minute game asset](../five-minute-game-asset/).

<!-- docs:if provider_bootstrap.production_verified -->
## Automated bootstrap

Verified provider contracts support automated bootstrap modes (provision, validate, bind, rotate) through Hydracept tooling. Use automated bootstrap when your provider contract is production-verified.
<!-- docs:endif -->

<!-- docs:if !provider_bootstrap.production_verified -->
## Automated bootstrap

Automated provider bootstrap is not available for production yet. Use the manual create → bind flow above until provider contracts are marked production-verified.
<!-- docs:endif -->

<!-- docs:if inference_sources.local_inference -->
## Local inference

Local and private inference endpoints are available as an execution source for eligible capabilities.
<!-- docs:endif -->

## Next

- [Capabilities](../capabilities/)
- [Durable Jobs & Receipts](../jobs/)
- [Errors](../errors/)
