using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Import;

namespace Hydracept.Unity.Editor.Jobs
{
    public static class HydraceptJobs
    {
        private static JobService? TryCreateService()
        {
            var root = WorkspaceLocator.FindProjectRoot();
            if (string.IsNullOrWhiteSpace(root))
            {
                return null;
            }

            var workspace = WorkspaceReader.Resolve(root);
            var client = HydraceptConnection.CreateClient();
            if (client == null || workspace.State != WorkspaceState.Ready)
            {
                return null;
            }

            return new JobService(client, workspace, root);
        }

        public static Task<HydraceptJob?> SubmitAsync(
            string capabilityKey,
            Dictionary<string, object> input,
            string? prompt = null,
            CancellationToken cancellationToken = default)
        {
            var service = TryCreateService();
            if (service == null)
            {
                return Task.FromResult<HydraceptJob?>(null);
            }

            return service.SubmitAsync(capabilityKey, input, prompt, cancellationToken)
                .ContinueWith(task => (HydraceptJob?)task.Result, cancellationToken);
        }

        public static async Task<HydraceptJob?> GetAsync(
            string jobId,
            CancellationToken cancellationToken = default)
        {
            var service = TryCreateService();
            if (service == null)
            {
                return null;
            }

            return await service.GetAsync(jobId, cancellationToken);
        }

        public static async Task<ProjectJobListResponse?> ListRecentAsync(
            int limit = 25,
            string? cursor = null,
            CancellationToken cancellationToken = default)
        {
            var service = TryCreateService();
            if (service == null)
            {
                return null;
            }

            return await service.ListRecentAsync(limit, cursor, cancellationToken);
        }
    }
}
