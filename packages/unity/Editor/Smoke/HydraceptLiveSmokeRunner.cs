using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Import;
using Hydracept.Unity.Editor.Jobs;
using UnityEditor;
using UnityEngine;

namespace Hydracept.Unity.Editor.Smoke
{
    public static class HydraceptLiveSmokeRunner
    {
        private const int PollIntervalMs = 4000;
        private const int PollTimeoutMs = 600_000;
        private const string Prompt = "cute slime enemy icon, flat game art, simple silhouette";

        public static void RunBatchLiveSmoke()
        {
            RunAsync().GetAwaiter().GetResult();
        }

        private static async Task RunAsync()
        {
            var root = WorkspaceLocator.FindProjectRoot();
            if (string.IsNullOrWhiteSpace(root))
            {
                Fail("Could not locate Unity project root.");
            }

            var workspace = WorkspaceReader.Resolve(root);
            if (workspace.State != WorkspaceState.Ready)
            {
                Fail($"Workspace not ready: {workspace.State}");
            }

            Debug.Log($"[HydraceptLiveSmoke] workspace=Ready project={workspace.ProjectId}");

            var client = HydraceptConnection.CreateClient();
            if (client == null)
            {
                Fail("Could not create API client.");
            }

            var input = new Dictionary<string, object>
            {
                ["prompt"] = Prompt,
                ["requestTransparentOutput"] = true,
                ["variantCount"] = 1,
                ["width"] = 1024,
                ["height"] = 1024,
            };

            var service = new JobService(client, workspace, root);
            Debug.Log("[HydraceptLiveSmoke] submitting image.generate.v1 job...");
            var job = await service.SubmitAsync("image.generate.v1", input, Prompt);
            Debug.Log($"[HydraceptLiveSmoke] submitted job={job.JobId} status={job.Status}");

            var cached = false;
            foreach (var cachedJob in JobCache.NonTerminalJobs(root))
            {
                if (cachedJob.JobId == job.JobId)
                {
                    cached = true;
                    break;
                }
            }

            if (!cached)
            {
                Fail("Job was not persisted in cache after submit.");
            }

            var deadline = DateTime.UtcNow.AddMilliseconds(PollTimeoutMs);
            while (!JobCache.IsTerminal(job.Status) && DateTime.UtcNow < deadline)
            {
                Thread.Sleep(PollIntervalMs);
                job = await client.GetJobAsync(job.JobId);
                JobCache.UpdateStatus(root, job.JobId, job.Status);
                Debug.Log($"[HydraceptLiveSmoke] poll status={job.Status} artifacts={job.Artifacts.Count}");
            }

            if (!JobCache.IsTerminal(job.Status))
            {
                Fail($"Job timed out with status={job.Status}");
            }

            if (job.Status != "succeeded")
            {
                Fail($"Job failed with status={job.Status}");
            }

            if (job.Artifacts.Count < 1)
            {
                Fail("Job succeeded without downloadable artifacts.");
            }

            var destination = "Assets/Generated/Hydracept/live-smoke";
            var options = new ArtifactImportOptions
            {
                DestinationRoot = destination,
                Profile = ImageImportProfileKind.Sprite,
                CapabilityKey = job.CapabilityKey,
                ReceiptId = job.ReceiptId,
            };

            Debug.Log("[HydraceptLiveSmoke] importing artifacts...");
            var import = await ArtifactImporter.ImportAllAsync(client, job, options);
            if (!import.Success)
            {
                Fail($"Import failed: {import.Error}");
            }

            if (import.ImportedAssetPaths.Count < 1)
            {
                Fail("Import succeeded but no assets were written.");
            }

            if (string.IsNullOrWhiteSpace(import.ProvenancePath) || !File.Exists(import.ProvenancePath))
            {
                Fail("Provenance file missing after import.");
            }

            foreach (var path in import.ImportedAssetPaths)
            {
                var importer = AssetImporter.GetAtPath(path) as TextureImporter;
                if (importer == null || importer.textureType != TextureImporterType.Sprite)
                {
                    Fail($"Asset is not configured as sprite: {path}");
                }
            }

            Debug.Log(
                $"[HydraceptLiveSmoke] imported={import.ImportedAssetPaths.Count} provenance={import.ProvenancePath}");
            Debug.Log("[HydraceptLiveSmoke] PASS");
            EditorApplication.Exit(0);
        }

        private static void Fail(string message)
        {
            Debug.LogError($"[HydraceptLiveSmoke] FAIL: {message}");
            EditorApplication.Exit(1);
            throw new InvalidOperationException(message);
        }
    }
}
