using System.Text.Json.Serialization;

namespace Hydracept.Client;

/// <summary>hydracept.run-result.v1 semantic contract. Language API may differ; fields must not.</summary>
public sealed class HydraceptRunResult
{
    [JsonPropertyName("schemaVersion")]
    public string SchemaVersion { get; set; } = "hydracept.run-result.v1";

    [JsonPropertyName("capability")]
    public string Capability { get; set; } = "";

    [JsonPropertyName("jobId")]
    public string? JobId { get; set; }

    [JsonPropertyName("executionId")]
    public string? ExecutionId { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; } = "unknown";

    [JsonPropertyName("output")]
    public object? Output { get; set; }

    [JsonPropertyName("typedOutput")]
    public object? TypedOutput { get; set; }

    [JsonPropertyName("artifacts")]
    public List<HydraceptRunArtifact> Artifacts { get; set; } = [];

    [JsonPropertyName("pricing")]
    public HydraceptRunPricing Pricing { get; set; } = new();

    [JsonPropertyName("receipt")]
    public object? Receipt { get; set; }

    [JsonPropertyName("idempotencyKey")]
    public string? IdempotencyKey { get; set; }

    [JsonPropertyName("error")]
    public object? Error { get; set; }

    [JsonPropertyName("diagnostics")]
    public object? Diagnostics { get; set; }
}

public sealed class HydraceptRunArtifact
{
    [JsonPropertyName("artifactId")]
    public string ArtifactId { get; set; } = "";

    [JsonPropertyName("mediaType")]
    public string MediaType { get; set; } = "application/octet-stream";

    [JsonPropertyName("sha256")]
    public string? Sha256 { get; set; }

    [JsonPropertyName("byteLength")]
    public int? ByteLength { get; set; }

    [JsonPropertyName("remoteRef")]
    public string? RemoteRef { get; set; }

    [JsonPropertyName("localPath")]
    public string? LocalPath { get; set; }

    [JsonPropertyName("verified")]
    public bool Verified { get; set; }
}

public sealed class HydraceptRunPricing
{
    [JsonPropertyName("estimatedCost")]
    public double? EstimatedCost { get; set; }

    [JsonPropertyName("actualCost")]
    public double? ActualCost { get; set; }

    [JsonPropertyName("currency")]
    public string Currency { get; set; } = "USD";
}

public sealed class HydraceptRunOptions
{
    public bool Wait { get; set; } = true;
    public TimeSpan? Timeout { get; set; }
    public double? MaxCostUsd { get; set; }
    public string? IdempotencyKey { get; set; }
    public string? Out { get; set; }
}
