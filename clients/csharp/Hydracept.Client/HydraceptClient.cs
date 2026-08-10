using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Hydracept.Client;

/// <summary>
/// Thin Hydracept transport client. Configure <see cref="HttpClient.BaseAddress"/> and Bearer auth on the
/// injected client (recommended for DI), or pass <see cref="HydraceptClientOptions"/>.
/// </summary>
public sealed class HydraceptClient : IHydraceptClient
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    private readonly HttpClient _http;

    public HydraceptClient(HttpClient http)
        : this(http, options: null)
    {
    }

    public HydraceptClient(HttpClient http, HydraceptClientOptions? options)
    {
        _http = http ?? throw new ArgumentNullException(nameof(http));
        if (options is null)
            return;

        if (!string.IsNullOrWhiteSpace(options.BaseUrl)
            && Uri.TryCreate(options.BaseUrl, UriKind.Absolute, out var baseUri))
        {
            _http.BaseAddress = baseUri;
        }

        if (!string.IsNullOrWhiteSpace(options.BearerToken))
        {
            _http.DefaultRequestHeaders.Authorization =
                new AuthenticationHeaderValue("Bearer", options.BearerToken);
        }
    }

    public Task<JsonElement> InvokeAsync(object body, CancellationToken cancellationToken = default) =>
        PostJsonAsync("v1/invocations", body, headers: null, cancellationToken);

    public Task<JsonElement> GetInvocationAsync(string executionId, CancellationToken cancellationToken = default) =>
        GetJsonAsync($"v1/invocations/{Uri.EscapeDataString(executionId)}", cancellationToken);

    public Task<JsonElement> GetReceiptAsync(string executionId, CancellationToken cancellationToken = default) =>
        GetJsonAsync($"v1/invocations/{Uri.EscapeDataString(executionId)}/receipt", cancellationToken);

    public Task<JsonElement> CancelInvocationAsync(string executionId, CancellationToken cancellationToken = default) =>
        PostJsonAsync($"v1/invocations/{Uri.EscapeDataString(executionId)}/cancel", body: null, headers: null, cancellationToken);

    public async IAsyncEnumerable<HydraceptSseEvent> StreamInvocationEventsAsync(
        string executionId,
        string? lastEventId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Get,
            $"v1/invocations/{Uri.EscapeDataString(executionId)}/events");
        request.Headers.Accept.ParseAdd("text/event-stream");
        if (!string.IsNullOrWhiteSpace(lastEventId))
            request.Headers.TryAddWithoutValidation("Last-Event-ID", lastEventId);

        using var response = await _http
            .SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken)
            .ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            var err = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
            throw new HydraceptApiException(
                $"Hydracept SSE failed ({(int)response.StatusCode}): {err}",
                (int)response.StatusCode,
                err,
                executionId: executionId);
        }

        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        await foreach (var evt in HydraceptSseReader.ReadAsync(stream, cancellationToken).ConfigureAwait(false))
            yield return evt;
    }

    public Task<JsonElement> SubmitJobAsync(object body, CancellationToken cancellationToken = default) =>
        PostJsonAsync("v1/jobs", body, headers: null, cancellationToken);

    public Task<JsonElement> GetJobAsync(string jobId, CancellationToken cancellationToken = default) =>
        GetJsonAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}", cancellationToken);

    public Task<JsonElement> GetJobResultAsync(string jobId, CancellationToken cancellationToken = default) =>
        GetJsonAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}/result", cancellationToken);

    public Task<JsonElement> GetJobReceiptAsync(string jobId, CancellationToken cancellationToken = default) =>
        GetJsonAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}/receipt", cancellationToken);

    public Task<JsonElement> CancelJobAsync(string jobId, CancellationToken cancellationToken = default) =>
        PostJsonAsync($"v1/jobs/{Uri.EscapeDataString(jobId)}/cancel", body: null, headers: null, cancellationToken);

    public Task<JsonElement> SubmitVisualJobAsync(
        object body,
        string? idempotencyKey = null,
        CancellationToken cancellationToken = default)
    {
        IEnumerable<KeyValuePair<string, string>>? headers = null;
        if (!string.IsNullOrWhiteSpace(idempotencyKey))
        {
            headers = new[]
            {
                new KeyValuePair<string, string>("Idempotency-Key", idempotencyKey),
            };
        }

        return PostJsonAsync("v1/visual/jobs", body, headers, cancellationToken);
    }

    public Task<JsonElement> GetVisualJobAsync(string jobId, CancellationToken cancellationToken = default) =>
        GetJsonAsync($"v1/visual/jobs/{Uri.EscapeDataString(jobId)}", cancellationToken);

    public Task<byte[]> DownloadVisualAssetAsync(string assetIdOrPath, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(assetIdOrPath))
            throw new ArgumentException("Asset id or path is required.", nameof(assetIdOrPath));

        if (assetIdOrPath.StartsWith("v1/", StringComparison.OrdinalIgnoreCase)
            || assetIdOrPath.StartsWith('/'))
        {
            return GetBytesAsync(assetIdOrPath.TrimStart('/'), cancellationToken);
        }

        return GetBytesAsync($"v1/visual/assets/{Uri.EscapeDataString(assetIdOrPath)}", cancellationToken);
    }

    public Task<JsonElement> GetCapabilitiesAsync(CancellationToken cancellationToken = default) =>
        GetJsonAsync("v1/capabilities", cancellationToken);

    public Task<JsonElement> DescribeCapabilityAsync(
        string capabilityKey,
        CancellationToken cancellationToken = default) =>
        GetJsonAsync($"v1/capabilities/{Uri.EscapeDataString(capabilityKey)}", cancellationToken);

    public Task<JsonElement> InvokeCapabilityAsync(
        string capabilityKey,
        object body,
        CancellationToken cancellationToken = default) =>
        PostJsonAsync(
            $"v1/capabilities/{Uri.EscapeDataString(capabilityKey)}/invoke",
            body,
            headers: null,
            cancellationToken);

    public Task<JsonElement> SubmitCapabilityJobAsync(
        string capabilityKey,
        object body,
        CancellationToken cancellationToken = default) =>
        PostJsonAsync(
            $"v1/capabilities/{Uri.EscapeDataString(capabilityKey)}/jobs",
            body,
            headers: null,
            cancellationToken);

    public async Task<JsonElement> GetJsonAsync(string relativePath, CancellationToken cancellationToken = default)
    {
        var (status, body) = await GetJsonWithStatusAsync(relativePath, cancellationToken).ConfigureAwait(false);
        if ((int)status is < 200 or >= 300)
            throw ToApiException(status, body, bodyText: null, relativePath);
        return body;
    }

    /// <summary>GET JSON without throwing on non-success HTTP status (caller maps policy errors).</summary>
    public async Task<(System.Net.HttpStatusCode StatusCode, JsonElement Body)> GetJsonWithStatusAsync(
        string relativePath,
        CancellationToken cancellationToken = default)
    {
        using var response = await _http.GetAsync(Normalize(relativePath), cancellationToken).ConfigureAwait(false);
        var body = await ReadJsonAsync(response, cancellationToken, allowEmptySuccess: true).ConfigureAwait(false);
        return (response.StatusCode, body);
    }

    public async Task<JsonElement> PostJsonAsync(
        string relativePath,
        object? body,
        IEnumerable<KeyValuePair<string, string>>? headers = null,
        CancellationToken cancellationToken = default)
    {
        var (status, document) = await PostJsonWithStatusAsync(relativePath, body, headers, cancellationToken)
            .ConfigureAwait(false);
        if ((int)status is < 200 or >= 300)
            throw ToApiException(status, document, bodyText: null, relativePath);
        return document;
    }

    /// <summary>POST JSON without throwing on non-success HTTP status (caller maps policy errors).</summary>
    public async Task<(System.Net.HttpStatusCode StatusCode, JsonElement Body)> PostJsonWithStatusAsync(
        string relativePath,
        object? body,
        IEnumerable<KeyValuePair<string, string>>? headers = null,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, Normalize(relativePath));
        if (headers is not null)
        {
            foreach (var header in headers)
                request.Headers.TryAddWithoutValidation(header.Key, header.Value);
        }

        if (body is not null)
            request.Content = JsonContent.Create(body, options: JsonOptions);

        using var response = await _http.SendAsync(request, cancellationToken).ConfigureAwait(false);
        var document = await ReadJsonAsync(response, cancellationToken, allowEmptySuccess: true).ConfigureAwait(false);
        return (response.StatusCode, document);
    }

    public async Task PostEmptyAsync(string relativePath, CancellationToken cancellationToken = default)
    {
        using var response = await _http.PostAsync(Normalize(relativePath), content: null, cancellationToken)
            .ConfigureAwait(false);
        _ = await ReadJsonAsync(response, cancellationToken, allowEmptySuccess: true).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            throw new HydraceptApiException(
                $"Hydracept POST {relativePath} failed ({(int)response.StatusCode}).",
                (int)response.StatusCode);
        }
    }

    public async Task<byte[]> GetBytesAsync(string relativePath, CancellationToken cancellationToken = default)
    {
        using var response = await _http.GetAsync(Normalize(relativePath), cancellationToken).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            var err = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
            throw new HydraceptApiException(
                $"Hydracept GET {relativePath} failed ({(int)response.StatusCode}): {err}",
                (int)response.StatusCode,
                err);
        }

        return await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
    }

    private static string Normalize(string relativePath) =>
        relativePath.TrimStart('/');

    private static async Task<JsonElement> ReadJsonAsync(
        HttpResponseMessage response,
        CancellationToken cancellationToken,
        bool allowEmptySuccess = false)
    {
        var text = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
        if (string.IsNullOrWhiteSpace(text))
        {
            if (allowEmptySuccess || response.IsSuccessStatusCode)
                return default;

            throw new HydraceptApiException(
                $"Hydracept HTTP {(int)response.StatusCode} with empty body.",
                (int)response.StatusCode,
                errorCode: response.StatusCode == System.Net.HttpStatusCode.Unauthorized
                    ? "Unauthorized"
                    : "HttpError");
        }

        using var document = JsonDocument.Parse(text);
        return document.RootElement.Clone();
    }

    private static HydraceptApiException ToApiException(
        System.Net.HttpStatusCode statusCode,
        JsonElement document,
        string? bodyText,
        string? path = null)
    {
        var code = ReadString(document, "code")
            ?? ReadNestedString(document, "detail", "code")
            ?? statusCode.ToString();
        var message = ReadString(document, "message")
            ?? ReadNestedString(document, "detail", "message")
            ?? (path is null
                ? $"Hydracept rejected request with HTTP {(int)statusCode}."
                : $"Hydracept {path} failed ({(int)statusCode}).");
        var executionId = ReadString(document, "executionId")
            ?? ReadNestedString(document, "detail", "executionId");
        var receiptId = ReadString(document, "receiptId")
            ?? ReadNestedString(document, "detail", "receiptId");

        return new HydraceptApiException(
            message,
            (int)statusCode,
            bodyText,
            code,
            executionId,
            receiptId);
    }

    private static string? ReadString(JsonElement document, string property)
    {
        if (document.ValueKind != JsonValueKind.Object)
            return null;
        if (!document.TryGetProperty(property, out var el) || el.ValueKind != JsonValueKind.String)
            return null;
        return el.GetString();
    }

    private static string? ReadNestedString(JsonElement document, string parent, string property)
    {
        if (document.ValueKind != JsonValueKind.Object)
            return null;
        if (!document.TryGetProperty(parent, out var nested) || nested.ValueKind != JsonValueKind.Object)
            return null;
        return ReadString(nested, property);
    }
}
