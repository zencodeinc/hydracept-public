namespace Hydracept.Client;

public sealed class HydraceptClientOptions
{
    /// <summary>Absolute Hydracept base URL, e.g. http://localhost:8080</summary>
    public string? BaseUrl { get; set; }

    /// <summary>Bearer service token. Prefer configuring Authorization on the injected HttpClient.</summary>
    public string? BearerToken { get; set; }

    /// <summary>
    /// When true, relative paths are treated as already including the /v1 prefix (or not).
    /// Default false: convenience methods use v1/... paths relative to BaseAddress.
    /// </summary>
    public bool PathsIncludeV1Prefix { get; set; } = true;
}
