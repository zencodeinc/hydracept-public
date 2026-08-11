using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;

namespace Hydracept.Unity.Editor.Jobs
{
    public sealed class JobService
    {
        private readonly HydraceptApiClient _client;
        private readonly ResolvedWorkspace _workspace;
        private readonly string _projectRoot;

        public JobService(HydraceptApiClient client, ResolvedWorkspace workspace, string projectRoot)
        {
            _client = client;
            _workspace = workspace;
            _projectRoot = projectRoot;
        }

        public async Task<HydraceptJob> SubmitAsync(
            string capabilityKey,
            Dictionary<string, object> input,
            string? prompt = null,
            CancellationToken cancellationToken = default)
        {
            var request = _client.BuildJobRequest(
                _workspace.ProductId,
                _workspace.ProjectId,
                _workspace.Environment,
                input,
                Guid.NewGuid().ToString("N"));

            var job = await _client.SubmitCapabilityJobAsync(capabilityKey, request, cancellationToken);
            JobCache.Upsert(_projectRoot, job.JobId, capabilityKey, prompt, job.Status);
            return job;
        }

        public Task<HydraceptJob> GetAsync(string jobId, CancellationToken cancellationToken = default) =>
            _client.GetJobAsync(jobId, cancellationToken);

        public Task<HydraceptReceipt> GetReceiptAsync(string jobId, CancellationToken cancellationToken = default) =>
            _client.GetReceiptAsync(jobId, cancellationToken);

        public Task<ProjectJobListResponse> ListRecentAsync(
            int limit = 25,
            string? cursor = null,
            CancellationToken cancellationToken = default) =>
            _client.ListProjectJobsAsync(_workspace.ProjectId, limit, cursor, cancellationToken);
    }
}
