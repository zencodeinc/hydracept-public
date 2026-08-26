# Integrating safely

Use the public Hydracept API as the single path from your product to the AI providers it uses.

## Rule

This keeps credentials, provider configuration, job status, and execution records in one place.

When Hydracept is meant to own generation execution:

- call Hydracept capabilities and jobs from trusted tooling or your server
- keep provider SDKs out of the generation path handled by Hydracept
- never embed provider keys in game clients or other shipped public code

## CI gate

<!-- docs:if packages.cli.releasePublished -->
```bash
hydracept consumer-check --strict
```

Add a CI check if you want to prevent direct provider clients from entering paths handled by Hydracept.
<!-- docs:endif -->

<!-- docs:if !packages.cli.releasePublished -->
When the CLI release is published, add the consumer-check gate to product CI. Until then, review integrations manually against this boundary and the public OpenAPI contract.
<!-- docs:endif -->

## Related

- [Capabilities](../capabilities/)
- [Coding Agents](../agents/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
