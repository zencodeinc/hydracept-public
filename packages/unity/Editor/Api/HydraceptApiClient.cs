using System;
using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api.Generated;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine.Networking;

namespace Hydracept.Unity.Editor.Api
{
    public sealed class HydraceptApiClient
    {
        private readonly string _baseUrl;
        private readonly string _bearerToken;

        public HydraceptApiClient(string baseUrl, string bearerToken)
        {
            _baseUrl = (baseUrl ?? string.Empty).TrimEnd('/');
            _bearerToken = bearerToken ?? string.Empty;
        }

        public Task<JObject> GetCapabilitiesAsync(CancellationToken cancellationToken = default) =>
            GetJsonAsync<JObject>("v1/capabilities", cancellationToken);

        public Task<HydraceptJob> SubmitCapabilityJobAsync(
            string capabilityKey,
            CapabilityJobRequest request,
            CancellationToken cancellationToken = default) =>
            PostJsonAsync<CapabilityJobRequest, HydraceptJob>(
                $"v1/capabilities/{Uri.EscapeDataString(capabilityKey)}/jobs",
                request,
                cancellationToken);

        public Task<HydraceptJob> GetJobAsync(string jobId, CancellationToken cancellationToken = default) =>
            GetJsonAsync<HydraceptJob>($"v1/jobs/{Uri.EscapeDataString(jobId)}", cancellationToken);

        public Task<HydraceptReceipt> GetReceiptAsync(string jobId, CancellationToken cancellationToken = default) =>
            GetJsonAsync<HydraceptReceipt>($"v1/jobs/{Uri.EscapeDataString(jobId)}/receipt", cancellationToken);

        public Task<Dictionary<string, object>> GetJobRequestAsync(
            string jobId,
            CancellationToken cancellationToken = default) =>
            GetJsonAsync<Dictionary<string, object>>(
                $"v1/jobs/{Uri.EscapeDataString(jobId)}/request",
                cancellationToken);

        public Task<ProjectJobListResponse> ListProjectJobsAsync(
            string projectId,
            int limit = 25,
            string? cursor = null,
            CancellationToken cancellationToken = default)
        {
            var path = $"v1/projects/{Uri.EscapeDataString(projectId)}/jobs?limit={limit}";
            if (!string.IsNullOrWhiteSpace(cursor))
            {
                path += $"&cursor={Uri.EscapeDataString(cursor)}";
            }

            return GetJsonAsync<ProjectJobListResponse>(path, cancellationToken);
        }

        public Task<Dictionary<string, object>> GetDiagnosticsSessionAsync(
            CancellationToken cancellationToken = default) =>
            GetJsonAsync<Dictionary<string, object>>("v1/diagnostics/session", cancellationToken);

        public Task<byte[]> DownloadArtifactAsync(
            string jobId,
            string artifactId,
            CancellationToken cancellationToken = default) =>
            GetBytesAsync(
                $"v1/jobs/{Uri.EscapeDataString(jobId)}/artifacts/{Uri.EscapeDataString(artifactId)}",
                cancellationToken);

        public CapabilityJobRequest BuildJobRequest(
            string productId,
            string projectId,
            string environment,
            Dictionary<string, object> input,
            string idempotencyKey)
        {
            return new CapabilityJobRequest
            {
                Context = new CapabilityContext
                {
                    ProductId = productId,
                    ProjectId = projectId,
                    Environment = environment,
                },
                Input = input,
                Execution = new CapabilityExecutionOptions
                {
                    ExecutionPreference = "automatic",
                },
                IdempotencyKey = idempotencyKey,
            };
        }

        private async Task<T> GetJsonAsync<T>(string relativePath, CancellationToken cancellationToken)
        {
            using var request = CreateRequest(UnityWebRequest.Get(Normalize(relativePath)));
            return await SendJsonAsync<T>(request, cancellationToken);
        }

        private async Task<TResponse> PostJsonAsync<TRequest, TResponse>(
            string relativePath,
            TRequest body,
            CancellationToken cancellationToken)
        {
            var json = JsonConvert.SerializeObject(body);
            using var request = CreateRequest(
                new UnityWebRequest(Normalize(relativePath), UnityWebRequest.kHttpVerbPOST));
            var bytes = Encoding.UTF8.GetBytes(json);
            request.uploadHandler = new UploadHandlerRaw(bytes);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            return await SendJsonAsync<TResponse>(request, cancellationToken);
        }

        private static void WaitForRequest(UnityWebRequestAsyncOperation operation, CancellationToken cancellationToken)
        {
            while (!operation.isDone)
            {
                cancellationToken.ThrowIfCancellationRequested();
                Thread.Sleep(15);
            }
        }

        private async Task<byte[]> GetBytesAsync(string relativePath, CancellationToken cancellationToken)
        {
            using var request = CreateRequest(UnityWebRequest.Get(Normalize(relativePath)));
            var operation = request.SendWebRequest();
            WaitForRequest(operation, cancellationToken);

            if (request.result != UnityWebRequest.Result.Success)
            {
                throw new HydraceptApiException(
                    $"Hydracept download failed ({request.responseCode}): {request.error}",
                    (int)request.responseCode);
            }

            return request.downloadHandler.data;
        }

        private async Task<T> SendJsonAsync<T>(UnityWebRequest request, CancellationToken cancellationToken)
        {
            var operation = request.SendWebRequest();
            WaitForRequest(operation, cancellationToken);

            var body = request.downloadHandler?.text ?? string.Empty;
            if (request.result != UnityWebRequest.Result.Success)
            {
                throw new HydraceptApiException(
                    $"Hydracept request failed ({request.responseCode}): {body}",
                    (int)request.responseCode);
            }

            if (string.IsNullOrWhiteSpace(body))
            {
                return default!;
            }

            return JsonConvert.DeserializeObject<T>(body)!;
        }

        private UnityWebRequest CreateRequest(UnityWebRequest request)
        {
            request.downloadHandler ??= new DownloadHandlerBuffer();
            request.SetRequestHeader("Authorization", $"Bearer {_bearerToken}");
            request.SetRequestHeader("Accept", "application/json");
            return request;
        }

        private string Normalize(string relativePath) => $"{_baseUrl}/{relativePath.TrimStart('/')}";
    }
}
