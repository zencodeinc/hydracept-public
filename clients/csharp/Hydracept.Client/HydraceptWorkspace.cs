using System.Text.Json;
using System.Text.Json.Nodes;

namespace Hydracept.Client;

/// <summary>Checkout identity from .hydracept/project.json. Open() never takes a project-id override.</summary>
public sealed class HydraceptWorkspace : IDisposable
{
    public HydraceptClient Client { get; }
    public HydraceptJobRunner Jobs { get; }
    public string Root { get; }
    public string ProjectId { get; }

    private HydraceptWorkspace(HydraceptClient client, HydraceptJobRunner jobs, string root, string projectId)
    {
        Client = client;
        Jobs = jobs;
        Root = root;
        ProjectId = projectId;
    }

    public static HydraceptWorkspace Open(string? root = null)
    {
        var projectRoot = Path.GetFullPath(root ?? Directory.GetCurrentDirectory());
        var bindingPath = Path.Combine(projectRoot, ".hydracept", "project.json");
        if (!File.Exists(bindingPath))
            throw new InvalidOperationException("Missing .hydracept/project.json — run python -m hydracept init");

        using var bindingDoc = JsonDocument.Parse(File.ReadAllText(bindingPath));
        var binding = bindingDoc.RootElement;
        var projectId = binding.GetProperty("projectId").GetString()
            ?? throw new InvalidOperationException("project.json is missing projectId");
        var envProject = Environment.GetEnvironmentVariable("HYDRACEPT_PROJECT")
            ?? Environment.GetEnvironmentVariable("HYDRACEPT_PROJECT_ID");
        if (!string.IsNullOrWhiteSpace(envProject) && envProject != projectId)
        {
            throw new InvalidOperationException(
                $"HYDRACEPT_PROJECT={envProject} disagrees with project.json projectId={projectId}");
        }

        var apiOrigin = "https://api.hydracept.com";
        if (binding.TryGetProperty("apiOrigin", out var originEl))
            apiOrigin = originEl.GetString() ?? apiOrigin;
        var environment = "development";
        if (binding.TryGetProperty("environment", out var envEl))
            environment = envEl.GetString() ?? environment;

        var secretsPath = Path.Combine(projectRoot, ".hydracept", "secrets.json");
        var token = Environment.GetEnvironmentVariable("HYDRACEPT_API_KEY");
        if (string.IsNullOrWhiteSpace(token) && File.Exists(secretsPath))
        {
            using var secretsDoc = JsonDocument.Parse(File.ReadAllText(secretsPath));
            if (secretsDoc.RootElement.TryGetProperty("apiKey", out var keyEl))
                token = keyEl.GetString();
            else if (secretsDoc.RootElement.TryGetProperty("token", out var tokEl))
                token = tokEl.GetString();
        }
        if (string.IsNullOrWhiteSpace(token))
            throw new InvalidOperationException("No workspace API key in secrets.json");

        var http = new HttpClient { BaseAddress = new Uri(apiOrigin.TrimEnd('/') + "/") };
        var client = new HydraceptClient(http, new HydraceptClientOptions
        {
            BaseUrl = apiOrigin,
            BearerToken = token,
        });
        var jobs = new HydraceptJobRunner(client, projectId, environment);
        return new HydraceptWorkspace(client, jobs, projectRoot, projectId);
    }

    public async Task<HydraceptRunResult> RunAsync(
        string capabilityKey,
        object body,
        HydraceptRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        options ??= new HydraceptRunOptions();
        await EnsureExecutionProjectAsync(cancellationToken).ConfigureAwait(false);
        var key = string.IsNullOrWhiteSpace(options.IdempotencyKey)
            ? $"run-{Guid.NewGuid():N}"
            : options.IdempotencyKey;
        var payload = BuildRunPayload(body, key, options.MaxCostUsd);
        if (!options.Wait)
        {
            var submitted = await Client.SubmitCapabilityJobAsync(capabilityKey, payload, cancellationToken)
                .ConfigureAwait(false);
            var jobId = submitted.TryGetProperty("jobId", out var idEl) ? idEl.GetString() : null;
            if (string.IsNullOrWhiteSpace(jobId) && submitted.TryGetProperty("id", out var altEl))
                jobId = altEl.GetString();
            if (string.IsNullOrWhiteSpace(jobId))
                throw new InvalidOperationException("No jobId in submit response");
            return new HydraceptRunResult
            {
                Capability = capabilityKey,
                JobId = jobId,
                ExecutionId = jobId,
                Status = "running",
                IdempotencyKey = key,
                Pricing = PricingFrom(submitted, null),
            };
        }
        var result = await Jobs.RunAsync(
            capabilityKey,
            payload,
            downloadDir: options.Out,
            pollFor: options.Timeout,
            outputRoot: string.IsNullOrWhiteSpace(options.Out) ? Root : null,
            cancellationToken: cancellationToken)
            .ConfigureAwait(false);
        return new HydraceptRunResult
        {
            Capability = capabilityKey,
            JobId = result.JobId,
            ExecutionId = result.JobId,
            Status = result.Status,
            IdempotencyKey = key,
            Receipt = result.Receipt,
            Pricing = PricingFrom(result.Job, result.Receipt),
            Artifacts = result.Downloads.Select(path => new HydraceptRunArtifact
            {
                LocalPath = path,
                Verified = true,
            }).ToList(),
        };
    }

    internal static JsonObject BuildRunPayload(object body, string idempotencyKey, double? maxCostUsd)
    {
        JsonObject payload;
        var node = JsonSerializer.SerializeToNode(body);
        if (node is JsonObject obj)
            payload = obj;
        else
            payload = new JsonObject { ["input"] = node };

        var looksLikeEnvelope = payload["input"] is not null
            || payload["context"] is not null
            || payload["execution"] is not null
            || payload["idempotencyKey"] is not null;
        if (!looksLikeEnvelope)
            payload = new JsonObject { ["input"] = payload };

        payload["idempotencyKey"] = idempotencyKey;
        if (maxCostUsd is { } maxCost)
        {
            var execution = payload["execution"] as JsonObject ?? new JsonObject();
            var constraints = execution["executionConstraints"] as JsonObject ?? new JsonObject();
            constraints["maxCostUsd"] = maxCost;
            execution["executionConstraints"] = constraints;
            payload["execution"] = execution;
        }
        return payload;
    }

    internal static HydraceptRunPricing PricingFrom(JsonElement job, JsonElement? receipt)
    {
        // Customer charge leads the contract; provider cost is an upstream basis,
        // never a retail price. Mirrors clients/typescript/src/run-result.ts and
        // the Python client's RunPricing projection.
        var source = receipt is { ValueKind: JsonValueKind.Object } rec ? rec : job;
        var pricing = ObjectOrNull(source, "pricing");
        var customerCharge = ObjectOrNull(source, "pricing", "charge", "customerCharge");
        var quote = ObjectOrNull(source, "pricing", "quote", "customerTotal");
        var reportedCost = ObjectOrNull(source, "pricing", "providerUsage", "reportedCost");
        var basisActual = ObjectOrNull(source, "pricing", "basisActual");
        var basisEstimated = ObjectOrNull(source, "pricing", "basisEstimated");
        var estimatedCharge = ObjectOrNull(source, "pricing", "estimatedCharge");

        var owed = MicrosToUsd(ReadDouble(customerCharge, "amountMicros"))
            ?? MicrosToUsd(ReadDouble(customerCharge, "customerTotalMicros"));
        var basis = MicrosToUsd(ReadDouble(basisActual, "amountMicros"))
            ?? MicrosToUsd(ReadDouble(ObjectOrNull(source, "pricing", "actualCharge"), "amountMicros"))
            ?? MicrosToUsd(ReadDouble(reportedCost, "amountMicros"));
        var estimatedBasis = MicrosToUsd(ReadDouble(basisEstimated, "amountMicros"));
        var estimated = MicrosToUsd(ReadDouble(estimatedCharge, "amountMicros"))
            ?? MicrosToUsd(ReadDouble(quote, "amountMicros"))
            ?? ReadDouble(job, "estimatedCost");

        var result = new HydraceptRunPricing
        {
            CustomerChargeUsd = owed,
            ChargeState = owed is null ? null : owed > 0 ? "charged" : "covered",
            BillingMode = ReadString(pricing, "mode"),
            ProviderCostUsd = basis,
            ProviderCostBasis = "upstream-price-basis",
            EstimatedProviderCostUsd = estimatedBasis,
            EstimatedCustomerChargeUsd = estimated,
            Currency = "USD",
        };
        if (owed is null && basis is null)
        {
            var legacy = ReadDouble(job, "actualCost");
            if (legacy is not null)
                result.LegacyActualCostUsd = legacy;
        }
        return result;
    }

    private static JsonElement? ObjectOrNull(JsonElement root, params string[] names)
    {
        var current = root;
        foreach (var name in names)
        {
            if (current.ValueKind != JsonValueKind.Object
                || !current.TryGetProperty(name, out var next)
                || next.ValueKind != JsonValueKind.Object)
                return null;
            current = next;
        }
        return current;
    }

    private static double? MicrosToUsd(double? micros)
        => micros is { } value ? value / 1_000_000d : null;

    private static double? ReadDouble(JsonElement? element, string name)
        => element is { } value ? ReadDouble(value, name) : null;

    private static double? ReadDouble(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var value)
            || value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
            return null;
        if (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number))
            return number;
        if (value.ValueKind == JsonValueKind.String
            && double.TryParse(value.GetString(), out var parsed))
            return parsed;
        return null;
    }

    private async Task EnsureExecutionProjectAsync(CancellationToken cancellationToken)
    {
        JsonElement diag;
        try
        {
            diag = await Client.GetJsonAsync("v1/diagnostics/session", cancellationToken)
                .ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException(
                "Cannot resolve an execution project — checkout and credential must match. "
                + "Run python -m hydracept doctor --fix",
                ex);
        }

        var token = ReadString(diag, "tokenProjectId")
            ?? ReadString(diag, "principalProjectId")
            ?? ReadString(diag, "projectId")
            ?? "";
        var home = "";
        try
        {
            var session = await Client.GetJsonAsync("v1/session/context", cancellationToken)
                .ConfigureAwait(false);
            if (session.TryGetProperty("project", out var project)
                && project.ValueKind == JsonValueKind.Object
                && project.TryGetProperty("id", out var idEl))
            {
                home = idEl.GetString() ?? "";
            }
        }
        catch (Exception)
        {
            home = "";
        }

        if (!string.IsNullOrEmpty(token) && token == home && token != ProjectId)
            token = "";
        if (string.IsNullOrEmpty(token))
        {
            throw new InvalidOperationException(
                "Cannot resolve an execution project — checkout and credential must match. "
                + "Run python -m hydracept doctor --fix");
        }
        if (token != ProjectId)
        {
            throw new InvalidOperationException(
                $"Checkout project {ProjectId} disagrees with credential project {token}. "
                + "Hydracept will not manufacture an execution project.");
        }
    }

    private static string? ReadString(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String)
            return null;
        var text = value.GetString();
        return string.IsNullOrWhiteSpace(text) ? null : text;
    }

    private static string? ReadString(JsonElement? element, string name)
        => element is { } value ? ReadString(value, name) : null;

    public void Dispose()
    {
    }
}
