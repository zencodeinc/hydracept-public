# Hydracept.Client

NuGet package for the Hydracept public HTTP + SSE client — an execution control plane for software and agents that need external capabilities.

```bash
dotnet add package Hydracept.Client
```

```csharp
var client = new HydraceptClient(new HydraceptClientOptions
{
    BaseUrl = "https://api.hydracept.com",
    BearerToken = Environment.GetEnvironmentVariable("HYDRACEPT_API_KEY"),
});

var pinned = await client.CreatePinnedInferenceAsync(new
{
    pin = new { provider = "openai", model = "gpt-5.6-sol", api = "responses" },
    isolation = "stateless",
    input = "ping",
});
```

Pinned Execution implements RIP (`POST /v1/inference/pinned`). Provenance helpers: `CreateRunManifestAsync`, `GetLockfileAsync`, `VerifyLockfileAsync`.

Docs: https://docs.hydracept.com

A Zencode company · © Zencode Consulting Inc.
