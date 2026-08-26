# Security

## Credentials

- Hydracept API keys authenticate callers to the API.
- Provider credentials (BYOK) pay for inference and are encrypted at rest.
- Do not embed Hydracept API keys or provider secrets in shipped game clients.
- For player-facing apps, call Hydracept from your server.

## Transport

All public API traffic uses HTTPS (`https://api.hydracept.com`).

## Least privilege

Bind provider credentials to the project/environment that needs them. Use separate machine credentials for CI and production when you can.

## Consumer boundary

For generation handled by Hydracept, route work through the Hydracept API instead of calling provider SDKs directly. See [Integrating safely](../consumer-boundary/).

## Reporting

Report security issues to [support@hydracept.com](mailto:support@hydracept.com).

## Related

- [Authentication & Activation](../authentication/)
- [Connections / BYOK](../connections/)
- [Privacy](https://hydracept.com/privacy.html)
- [Terms](https://hydracept.com/terms.html)
