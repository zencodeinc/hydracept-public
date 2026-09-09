using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Hydracept.Client;

/// <summary>Capability-job orchestration: submit, nextAction, poll, download, receipt.</summary>
public sealed class HydraceptJobRunner
{
    private readonly IHydraceptClient _client;
    private readonly string _projectId;
    private readonly string _environment;

    public HydraceptJobRunner(IHydraceptClient client, string projectId, string environment)
    {
        _client = client;
        _projectId = projectId;
        _environment = environment;
    }

    public static string NextAction(JsonElement job)
    {
        var status = job.TryGetProperty("status", out var st) ? st.GetString() ?? "" : "";
        var hasArtifacts = job.TryGetProperty("artifacts", out var arts)
            && arts.ValueKind == JsonValueKind.Array
            && arts.GetArrayLength() > 0;
        return status switch
        {
            "queued" or "running" or "awaiting_approval" or "canceling" => "poll",
            "succeeded" => hasArtifacts ? "download" : "receipt",
            _ => "done",
        };
    }

    public async Task<HydraceptJobRunResult> RunAsync(
        string capabilityKey,
        object body,
        string? downloadDir = null,
        TimeSpan? pollFor = null,
        string? outputRoot = null,
        CancellationToken cancellationToken = default)
    {
        var payload = MergeContext(body);
        var submitted = await _client.SubmitCapabilityJobAsync(capabilityKey, payload, cancellationToken)
            .ConfigureAwait(false);
        var jobId = submitted.TryGetProperty("jobId", out var idEl)
            ? idEl.GetString()
            : submitted.TryGetProperty("id", out var alt) ? alt.GetString() : null;
        if (string.IsNullOrWhiteSpace(jobId))
            throw new InvalidOperationException("No jobId in submit response");

        if (string.IsNullOrWhiteSpace(downloadDir) && !string.IsNullOrWhiteSpace(outputRoot))
            downloadDir = Path.Combine(outputRoot, ".hydracept", "output", jobId);

        DateTime? deadline = pollFor is { } timeout ? DateTime.UtcNow + timeout : null;
        JsonElement job = submitted;
        var status = "queued";
        while (true)
        {
            job = await _client.GetJobAsync(jobId, cancellationToken).ConfigureAwait(false);
            status = job.TryGetProperty("status", out var st) ? st.GetString() ?? "unknown" : "unknown";
            if (status is "succeeded" or "failed" or "canceled" or "cancelled")
                break;
            if (deadline is { } until && DateTime.UtcNow >= until)
                break;
            await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken).ConfigureAwait(false);
        }

        JsonElement? receipt = null;
        var downloads = new List<string>();
        if (status == "succeeded")
        {
            receipt = await _client.GetJobReceiptAsync(jobId, cancellationToken).ConfigureAwait(false);
            if (!string.IsNullOrWhiteSpace(downloadDir) && receipt is { } rec
                && rec.TryGetProperty("artifacts", out var artifacts)
                && artifacts.ValueKind == JsonValueKind.Array)
            {
                Directory.CreateDirectory(downloadDir);
                foreach (var item in artifacts.EnumerateArray())
                {
                    var artifactId = item.TryGetProperty("artifactId", out var aid)
                        ? aid.GetString()
                        : item.TryGetProperty("id", out var iid) ? iid.GetString() : null;
                    if (string.IsNullOrWhiteSpace(artifactId))
                        continue;
                    var bytes = await _client.DownloadJobArtifactAsync(jobId, artifactId, cancellationToken)
                        .ConfigureAwait(false);
                    var shaRaw = Sha256FromArtifact(item);
                    if (!string.IsNullOrWhiteSpace(shaRaw))
                    {
                        var expected = NormalizeSha256(shaRaw);
                        var actual = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
                        if (!string.IsNullOrWhiteSpace(expected) && expected != actual)
                            throw new InvalidOperationException($"SHA-256 mismatch for {artifactId}");
                    }
                    var filename = FilenameForDownload(item, artifactId!);
                    var target = Path.Combine(downloadDir, Path.GetFileName(filename ?? artifactId));
                    await File.WriteAllBytesAsync(target, bytes, cancellationToken).ConfigureAwait(false);
                    downloads.Add(target);
                }
            }
        }

        return new HydraceptJobRunResult(jobId, status, job, receipt, downloads, NextAction(job));
    }

    private object MergeContext(object body)
    {
        JsonObject payload;
        if (body is JsonElement el && el.ValueKind == JsonValueKind.Object)
        {
            payload = JsonNode.Parse(el.GetRawText())?.AsObject() ?? new JsonObject();
        }
        else if (body is JsonObject obj)
        {
            payload = obj;
        }
        else
        {
            var node = JsonSerializer.SerializeToNode(body);
            payload = node as JsonObject ?? new JsonObject { ["input"] = node };
        }

        var context = payload["context"] as JsonObject ?? new JsonObject();
        if (string.IsNullOrWhiteSpace(context["projectId"]?.ToString()))
            context["projectId"] = _projectId;
        if (string.IsNullOrWhiteSpace(context["productId"]?.ToString()))
            context["productId"] = _projectId;
        if (string.IsNullOrWhiteSpace(context["environment"]?.ToString()))
            context["environment"] = _environment;
        payload["context"] = context;
        if (payload["execution"] is JsonObject execution)
        {
            execution.Remove("quoteId");
            execution.Remove("estimateId");
        }
        return payload;
    }

    internal static string? Sha256FromArtifact(JsonElement item)
    {
        if (item.TryGetProperty("sha256", out var shaEl) && shaEl.ValueKind == JsonValueKind.String)
            return shaEl.GetString();
        if (item.TryGetProperty("digest", out var digest) && digest.ValueKind == JsonValueKind.Object
            && digest.TryGetProperty("sha256", out var nested) && nested.ValueKind == JsonValueKind.String)
            return nested.GetString();
        return null;
    }

    internal static string NormalizeSha256(string? value)
    {
        var raw = (value ?? "").Trim().ToLowerInvariant();
        return raw.StartsWith("sha256:", StringComparison.Ordinal) ? raw[7..] : raw;
    }

    internal static string FilenameForDownload(JsonElement item, string artifactId)
    {
        var media = "";
        if (item.TryGetProperty("mediaType", out var mt))
            media = mt.GetString() ?? "";
        else if (item.TryGetProperty("mimeType", out var mime))
            media = mime.GetString() ?? "";
        media = media.Split(';')[0].Trim().ToLowerInvariant();
        var raw = artifactId;
        if (item.TryGetProperty("filename", out var fn) && !string.IsNullOrWhiteSpace(fn.GetString()))
            raw = fn.GetString()!;
        else if (item.TryGetProperty("label", out var label) && !string.IsNullOrWhiteSpace(label.GetString()))
            raw = label.GetString()!;
        var name = Path.GetFileName(raw.Replace('\\', '/')) ?? "artifact";
        var ext = media switch
        {
            "audio/ogg" or "application/ogg" => ".ogg",
            "audio/wav" or "audio/x-wav" => ".wav",
            "audio/mpeg" or "audio/mp3" => ".mp3",
            "image/png" => ".png",
            "image/jpeg" or "image/jpg" => ".jpg",
            "image/webp" => ".webp",
            "model/gltf-binary" => ".glb",
            "video/mp4" => ".mp4",
            "application/json" => ".json",
            _ => "",
        };
        if (!string.IsNullOrEmpty(ext) && !name.EndsWith(ext, StringComparison.OrdinalIgnoreCase))
            name += ext;
        return name;
    }
}

public sealed record HydraceptJobRunResult(
    string JobId,
    string Status,
    JsonElement Job,
    JsonElement? Receipt,
    IReadOnlyList<string> Downloads,
    string NextAction);
