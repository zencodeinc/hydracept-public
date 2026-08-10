# Consumer Boundary

External products integrate as **customers of the public Hydracept surface**. They should not bypass Hydracept to reach providers directly.

## Rule

If an external customer cannot do it through the supported Hydracept surface, your product should not either.

When Hydracept is meant to own generation execution:

- call Hydracept capabilities and jobs
- do **not** call provider SDKs directly for that same generation path
- do **not** embed provider keys in game clients for Hydracept-owned work

## CI gate

<!-- docs:if packages.cli.releasePublished -->
```bash
hydracept consumer-check --strict
```

Fail the build when product code imports direct provider clients on paths Hydracept should own.
<!-- docs:endif -->

<!-- docs:if !packages.cli.releasePublished -->
When the CLI release is published, add the consumer-check gate to product CI. Until then, review integrations manually against this boundary and the public OpenAPI contract.
<!-- docs:endif -->

## Exceptions

Temporary exceptions need a named, expiring entry in `architecture/hydracept-consumer-exceptions.yaml` (platform policy). Do not add silent bypasses in product code.

## Related

- [Capabilities](../capabilities/)
- [Coding Agents](../agents/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
