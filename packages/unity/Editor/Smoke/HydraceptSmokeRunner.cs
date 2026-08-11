using System;
using System.IO;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Import;
using Hydracept.Unity.Editor.Jobs;
using UnityEditor;
using UnityEngine;

namespace Hydracept.Unity.Editor.Smoke
{
    public static class HydraceptSmokeRunner
    {
        public static void RunBatchSmoke()
        {
            var root = WorkspaceLocator.FindProjectRoot();
            if (string.IsNullOrWhiteSpace(root))
            {
                throw new InvalidOperationException("Could not locate Unity project root.");
            }

            var workspace = WorkspaceReader.Resolve(root);
            Debug.Log($"[HydraceptSmoke] workspace={workspace.State} project={workspace.ProjectId}");

            var unconfigured = workspace.State == WorkspaceState.Unconfigured;
            Debug.Log($"[HydraceptSmoke] unconfigured={unconfigured}");

            var preflight = ImportPreflight.ValidateBatch(
                "Assets/Generated/Hydracept/smoke",
                new[] { ("art_1", "frame_01.png"), ("art_2", "frame_02.png") });
            if (!preflight.Success)
            {
                throw new InvalidOperationException($"Preflight failed: {preflight.Error}");
            }

            JobCache.Upsert(root, "job_smoke_test", "image.generate.v1", "smoke prompt", "running");
            var cached = JobCache.Load(root);
            if (cached.Jobs.Count == 0)
            {
                throw new InvalidOperationException("Job cache persistence failed.");
            }

            var restored = false;
            foreach (var job in JobCache.NonTerminalJobs(root))
            {
                if (job.JobId == "job_smoke_test")
                {
                    restored = true;
                    break;
                }
            }

            if (!restored)
            {
                throw new InvalidOperationException("Nonterminal job recovery failed.");
            }

            Debug.Log("[HydraceptSmoke] PASS");
            EditorApplication.Exit(0);
        }
    }
}
