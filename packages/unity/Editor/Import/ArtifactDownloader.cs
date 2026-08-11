using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;

namespace Hydracept.Unity.Editor.Import
{
    public static class ArtifactDownloader
    {
        public static Task<string> DownloadToTempAsync(
            HydraceptApiClient client,
            string jobId,
            string artifactId,
            string fileName,
            CancellationToken cancellationToken = default)
        {
            var bytes = client.DownloadArtifactAsync(jobId, artifactId, cancellationToken)
                .GetAwaiter()
                .GetResult();
            var tempDir = Path.Combine(Path.GetTempPath(), "hydracept-unity", jobId);
            Directory.CreateDirectory(tempDir);
            var tempPath = Path.Combine(tempDir, ImportPreflight.SanitizeFileName(fileName));
            File.WriteAllBytes(tempPath, bytes);
            return Task.FromResult(tempPath);
        }
    }
}
