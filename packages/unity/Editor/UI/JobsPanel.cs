using System;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Import;
using Hydracept.Unity.Editor.Jobs;
using UnityEditor;
using UnityEngine.UIElements;

namespace Hydracept.Unity.Editor.UI
{
    public sealed class JobsPanel
    {
        private readonly VisualElement _root;
        private string? _nextCursor;

        public JobsPanel(VisualElement root)
        {
            _root = root;
        }

        public async Task RefreshAsync(string? cursor = null)
        {
            _root.Clear();
            var header = new VisualElement();
            header.AddToClassList("hydracept-row");
            header.Add(new Label("Recent Hydracept Jobs"));
            var refresh = new Button(() => _ = RefreshAsync()) { text = "Refresh" };
            header.Add(refresh);
            _root.Add(header);

            var response = await HydraceptJobs.ListRecentAsync(cursor: cursor);
            if (response == null)
            {
                _root.Add(new Label("Workspace not ready."));
                return;
            }

            _nextCursor = response.NextCursor;
            var rootPath = WorkspaceLocator.FindProjectRoot();
            var cache = rootPath == null ? new JobCacheDocument() : JobCache.Load(rootPath);

            foreach (var item in response.Items)
            {
                var row = new VisualElement();
                row.AddToClassList("hydracept-section");
                var cached = cache.Jobs.Find(job => job.JobId == item.JobId);
                var title = cached?.Prompt ?? item.JobId;
                row.Add(new Label($"{item.Status} — {item.CapabilityKey}"));
                row.Add(new Label(title));
                row.Add(new Label($"{item.ArtifactCount} artifacts"));
                row.Add(new Button(() => _ = OpenJobAsync(item.JobId)) { text = "Open" });
                _root.Add(row);
            }

            if (!string.IsNullOrWhiteSpace(_nextCursor))
            {
                _root.Add(new Button(() => _ = RefreshAsync(_nextCursor)) { text = "Load More" });
            }
        }

        private async Task OpenJobAsync(string jobId)
        {
            var client = HydraceptConnection.CreateClient();
            if (client == null)
            {
                return;
            }

            var detail = new VisualElement();
            detail.AddToClassList("hydracept-section");
            _root.Add(detail);

            try
            {
                var job = await client.GetJobAsync(jobId);
                detail.Add(new Label($"Job: {job.JobId}"));
                detail.Add(new Label($"Capability: {job.CapabilityKey}"));
                detail.Add(new Label($"Status: {job.Status}"));
                detail.Add(new Label($"Created: {job.CreatedAt}"));
                detail.Add(new Label($"Completed: {job.CompletedAt}"));

                HydraceptReceipt? receipt = null;
                if (!string.IsNullOrWhiteSpace(job.ReceiptId) || JobCache.IsTerminal(job.Status))
                {
                    try
                    {
                        receipt = await client.GetReceiptAsync(jobId);
                    }
                    catch (Exception)
                    {
                        // Receipt may not be ready for in-flight jobs.
                    }
                }

                ReceiptPanel.Render(detail, job, receipt);

                foreach (var artifact in job.Artifacts)
                {
                    var row = new VisualElement();
                    row.AddToClassList("hydracept-row");
                    row.Add(new Label(artifact.ArtifactId));
                    row.Add(new Button(() => _ = PreviewArtifact(client, job, artifact)) { text = "Preview" });
                    row.Add(new Button(() => _ = ImportArtifact(client, job, artifact)) { text = "Import" });
                    detail.Add(row);
                }

                if (job.Artifacts.Count > 0)
                {
                    detail.Add(new Button(() => _ = ImportAll(client, job)) { text = "Import All" });
                }

                var copyJob = new Button(() => EditorGUIUtility.systemCopyBuffer = job.JobId)
                {
                    text = "Copy Job ID",
                };
                detail.Add(copyJob);
            }
            catch (Exception ex)
            {
                detail.Add(new Label(ex.Message));
            }
        }

        private static async Task PreviewArtifact(
            HydraceptApiClient client,
            HydraceptJob job,
            HydraceptJobArtifactRef artifact)
        {
            var tempPath = await ArtifactDownloader.DownloadToTempAsync(
                client,
                job.JobId,
                artifact.ArtifactId,
                $"{artifact.ArtifactId}.png");
            EditorUtility.RevealInFinder(tempPath);
        }

        private static async Task ImportArtifact(
            HydraceptApiClient client,
            HydraceptJob job,
            HydraceptJobArtifactRef artifact)
        {
            var options = new ArtifactImportOptions
            {
                CapabilityKey = job.CapabilityKey,
                ReceiptId = job.ReceiptId,
            };
            await ArtifactImporter.ImportSingleAsync(client, job, artifact, options);
        }

        private static async Task ImportAll(HydraceptApiClient client, HydraceptJob job)
        {
            var options = new ArtifactImportOptions
            {
                CapabilityKey = job.CapabilityKey,
                ReceiptId = job.ReceiptId,
            };
            await ArtifactImporter.ImportAllAsync(client, job, options);
        }
    }
}
