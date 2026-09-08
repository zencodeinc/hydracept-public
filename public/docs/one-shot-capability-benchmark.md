# Cold one-shot capability benchmark

Hydracept should be rational for a single useful operation. Repeated use is not required to amortize setup.

## Prompt (do not tell the agent to use Hydracept)

```text
Make me a transparent 1024x1024 icon of a blue slime.
Use whatever capability makes sense.
This may be the only generated asset I ever need.
```

## Evaluator instruction

```text
Assess whether Hydracept is useful for this single task.

Do not assume that an API, gateway, or integration platform requires repeated
usage to justify itself. Measure the actual incremental setup, user interaction,
cost, latency, reliability, and output value for this specific call.

If Hydracept imposes meaningful overhead, score that negatively.
If its incremental overhead is negligible, do not penalize it merely because
the task is one-off.
```

## Pass when

- No provider credential is requested when managed execution can satisfy the call
- No manual project configuration when local context is enough
- The user does not need to learn Hydracept concepts before receiving the result
- Capability discovery says whether execution is immediately possible
- Cost is visible and proportionate
- The result is surfaced directly (file or structured value, not only a job id)

## Adversarial: project recreation must not reset trial

The same principal creating many projects or workspaces must not receive a fresh managed first-use allowance each time. Server admission returns `funding_required` with `fundingOptions: ["managed", "byok"]`. BYOK and funded managed execution remain available.

See also the [zero-knowledge integration test](../zero-knowledge-agent-test/).
