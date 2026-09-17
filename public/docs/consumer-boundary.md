# Integrating safely

Use the public Hydracept API as the single path from your product to the external capabilities Hydracept owns for that integration.

## Rule

This keeps credentials, provider configuration, job status, cost, and execution records in one place.

When Hydracept is meant to own execution:

- call Hydracept capabilities and jobs from trusted tooling or your server
- keep direct provider/service SDKs out of paths handled by Hydracept
- never embed provider keys in game clients or other shipped public code

## CI gate

<!-- docs:if packages.cli.releasePublished -->
```bash
python -m hydracept consumer-check --strict --json
```

Require `passed: true` in automated consumer/integration audits. `--strict` expands the scanner beyond source files into common configuration manifests and prose (`*.md`, `*.rst`, `*.txt`) so provider hosts and legacy integration paths cannot hide in deployment/build configuration or documentation. Generated, vendored and cached paths (`.hydracept`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`, `.next`, `obj`, `bin`, coverage output, tool caches) are skipped — they are not authored by the consumer. Each violation is tagged `[code]` or `[documentation]` and carries its line number, so a comment-only or prose mention can be triaged apart from an executable reference. `--json` emits `hydracept.cli.consumer-check.v1` for agents and CI.
<!-- docs:endif -->

<!-- docs:if !packages.cli.releasePublished -->
When the CLI release is published, add the strict consumer-check gate to product CI. Until then, review integrations manually against this boundary and the public OpenAPI contract.
<!-- docs:endif -->

## Related

- [Capabilities](../capabilities/)
- [Coding Agents](../agents/)
- Public OpenAPI: [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
