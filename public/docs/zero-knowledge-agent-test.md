# Public integration test

This test confirms that a coding agent can integrate Hydracept using the same public documentation, packages, API description, and agent guidance available to customers.

## Public materials

- PyPI `hydracept` and public `@hydracept/sdk`
- `GET /v1/agent-context` and `GET /v1/capabilities`
- [https://hydracept.com/openapi/hydracept-v1.json](https://hydracept.com/openapi/hydracept-v1.json)
- Public docs, examples, and `/.well-known/hydracept.json`
- Hosted MCP at `https://api.hydracept.com/mcp` (when using MCP path)

## Integration steps

```text
Integrate Hydracept using the official public materials:
1. pip install hydracept
2. python -m hydracept init --apply --yes --json
3. Submit an image generation job and retrieve its result
```

## Pass criteria

- Install from public registry only
- Bootstrap from agent-context / OpenAPI
- Submit `image.generate.v1` (or launch-advertised smoke capability)
- Poll job to terminal state and fetch receipt
- The execution record is available for review

## Automated runner

```bash
python scripts/run_clean_agent_integration.py
python scripts/run_clean_room_benchmark.py --tier integration --aided current
```

## Result format

Report the outcome, capability key, and job ID prefix.

For release-gating tiers, use `python scripts/run_clean_room_benchmark.py --tier integration --aided current` in the Hydracept repository CI.
