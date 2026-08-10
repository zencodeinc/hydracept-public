# Hydracept.Client

NuGet package for the Hydracept public HTTP + SSE client — one API for AI workloads in games.

```csharp
var client = new HydraceptClient(new HydraceptClientOptions
{
    BaseUrl = "https://api.hydracept.com",
    BearerToken = Environment.GetEnvironmentVariable("HYDRACEPT_API_KEY"),
});
```

Docs: https://docs.hydracept.com

A Zencode product · © Zencode Consulting Inc.
