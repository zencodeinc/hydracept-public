using System.Text.Json;

namespace Hydracept.Client;

/// <summary>
/// Language-neutral Hydracept HTTP transport. Product SDKs own routing, policy, and domain mapping.
/// </summary>
public interface IHydraceptClient
{
    Task<JsonElement> InvokeAsync(object body, CancellationToken cancellationToken = default);

    Task<JsonElement> GetInvocationAsync(string executionId, CancellationToken cancellationToken = default);

    Task<JsonElement> GetReceiptAsync(string executionId, CancellationToken cancellationToken = default);

    Task<JsonElement> CancelInvocationAsync(string executionId, CancellationToken cancellationToken = default);

    IAsyncEnumerable<HydraceptSseEvent> StreamInvocationEventsAsync(
        string executionId,
        string? lastEventId = null,
        CancellationToken cancellationToken = default);

    Task<JsonElement> SubmitJobAsync(object body, CancellationToken cancellationToken = default);

    Task<JsonElement> GetJobAsync(string jobId, CancellationToken cancellationToken = default);

    Task<JsonElement> GetJobResultAsync(string jobId, CancellationToken cancellationToken = default);

    Task<JsonElement> GetJobReceiptAsync(string jobId, CancellationToken cancellationToken = default);

    Task<JsonElement> CancelJobAsync(string jobId, CancellationToken cancellationToken = default);

    Task<JsonElement> SubmitVisualJobAsync(
        object body,
        string? idempotencyKey = null,
        CancellationToken cancellationToken = default);

    Task<JsonElement> GetVisualJobAsync(string jobId, CancellationToken cancellationToken = default);

    Task<byte[]> DownloadVisualAssetAsync(string assetIdOrPath, CancellationToken cancellationToken = default);

    Task<JsonElement> GetCapabilitiesAsync(CancellationToken cancellationToken = default);

    Task<JsonElement> DescribeCapabilityAsync(string capabilityKey, CancellationToken cancellationToken = default);

    Task<JsonElement> InvokeCapabilityAsync(
        string capabilityKey,
        object body,
        CancellationToken cancellationToken = default);

    Task<JsonElement> SubmitCapabilityJobAsync(
        string capabilityKey,
        object body,
        CancellationToken cancellationToken = default);

    Task<JsonElement> GetJsonAsync(string relativePath, CancellationToken cancellationToken = default);

    Task<(System.Net.HttpStatusCode StatusCode, JsonElement Body)> GetJsonWithStatusAsync(
        string relativePath,
        CancellationToken cancellationToken = default);

    Task<JsonElement> PostJsonAsync(
        string relativePath,
        object? body,
        IEnumerable<KeyValuePair<string, string>>? headers = null,
        CancellationToken cancellationToken = default);

    Task<(System.Net.HttpStatusCode StatusCode, JsonElement Body)> PostJsonWithStatusAsync(
        string relativePath,
        object? body,
        IEnumerable<KeyValuePair<string, string>>? headers = null,
        CancellationToken cancellationToken = default);

    Task PostEmptyAsync(string relativePath, CancellationToken cancellationToken = default);

    Task<byte[]> GetBytesAsync(string relativePath, CancellationToken cancellationToken = default);
}
