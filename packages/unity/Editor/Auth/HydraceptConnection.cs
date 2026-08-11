using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Newtonsoft.Json.Linq;

namespace Hydracept.Unity.Editor.Auth
{
    public sealed class HydraceptStatus
    {
        public WorkspaceState State { get; set; }
        public string ApiUrl { get; set; } = string.Empty;
        public string ProjectId { get; set; } = string.Empty;
        public string ProjectName { get; set; } = string.Empty;
        public string Environment { get; set; } = string.Empty;
        public List<string> Capabilities { get; set; } = new();
        public string? Error { get; set; }
    }

    public static class HydraceptConnection
    {
        public static ResolvedWorkspace GetWorkspace() =>
            WorkspaceReader.Resolve(WorkspaceLocator.FindProjectRoot());

        public static HydraceptApiClient? CreateClient()
        {
            var workspace = GetWorkspace();
            if (workspace.State == WorkspaceState.Unconfigured)
            {
                return null;
            }

            return new HydraceptApiClient(workspace.ApiUrl, workspace.Token);
        }

        public static async Task<HydraceptStatus> GetStatusAsync(CancellationToken cancellationToken = default)
        {
            var workspace = GetWorkspace();
            var status = new HydraceptStatus
            {
                State = workspace.State,
                ApiUrl = workspace.ApiUrl,
                ProjectId = workspace.ProjectId,
                ProjectName = workspace.ProjectName,
                Environment = workspace.Environment,
            };

            if (workspace.State != WorkspaceState.Ready)
            {
                return status;
            }

            var client = new HydraceptApiClient(workspace.ApiUrl, workspace.Token);
            try
            {
                var payload = await client.GetCapabilitiesAsync(cancellationToken);
                var capabilities = payload["capabilities"] as JArray;
                if (capabilities != null)
                {
                    foreach (var item in capabilities)
                    {
                        var key = item?["key"]?.ToString();
                        if (!string.IsNullOrWhiteSpace(key))
                        {
                            status.Capabilities.Add(key);
                        }
                    }
                }
            }
            catch (HydraceptApiException ex)
            {
                status.Error = ex.Message;
            }

            return status;
        }
    }
}
