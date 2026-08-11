using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Jobs;

namespace Hydracept.Unity.Editor.Import
{
    public static class HydraceptArtifacts
    {
        public static async Task<ArtifactImportResult?> ImportAsync(
            string jobId,
            string artifactId,
            ArtifactImportOptions options,
            CancellationToken cancellationToken = default)
        {
            var root = WorkspaceLocator.FindProjectRoot();
            var client = HydraceptConnection.CreateClient();
            if (root == null || client == null)
            {
                return null;
            }

            var job = await client.GetJobAsync(jobId, cancellationToken);
            var artifact = job.Artifacts.Find(item => item.ArtifactId == artifactId);
            if (artifact == null)
            {
                return new ArtifactImportResult
                {
                    Success = false,
                    Error = $"Artifact not found: {artifactId}",
                };
            }

            return await ArtifactImporter.ImportSingleAsync(client, job, artifact, options, cancellationToken);
        }

        public static async Task<ArtifactImportResult?> ImportAllAsync(
            string jobId,
            ArtifactImportOptions options,
            CancellationToken cancellationToken = default)
        {
            var client = HydraceptConnection.CreateClient();
            if (client == null)
            {
                return null;
            }

            var job = await client.GetJobAsync(jobId, cancellationToken);
            return await ArtifactImporter.ImportAllAsync(client, job, options, cancellationToken);
        }
    }
}
