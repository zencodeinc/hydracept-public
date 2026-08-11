using System;
using System.IO;
using System.Text.Json;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Import;
using Hydracept.Unity.Editor.Jobs;
using NUnit.Framework;

namespace Hydracept.Unity.Editor.Tests
{
    public sealed class WorkspaceReaderTests
    {
        [Test]
        public void Resolve_Unconfigured_WhenNoSecrets()
        {
            var root = CreateTempProject();
            var workspace = WorkspaceReader.Resolve(root);
            Assert.AreEqual(WorkspaceState.Unconfigured, workspace.State);
        }

        [Test]
        public void Resolve_Ready_FromConfigAndSecrets()
        {
            var root = CreateTempProject();
            WriteJson(Path.Combine(root, ".hydracept", "secrets.json"), new { apiKey = "test-key" });
            WriteJson(
                Path.Combine(root, ".hydracept", "config.json"),
                new
                {
                    apiBaseUrl = "https://api.example.com",
                    projectId = "cpr_test",
                    environment = "development",
                    productId = "my-game",
                });

            var workspace = WorkspaceReader.Resolve(root);
            Assert.AreEqual(WorkspaceState.Ready, workspace.State);
            Assert.AreEqual("test-key", workspace.Token);
            Assert.AreEqual("cpr_test", workspace.ProjectId);
            Assert.AreEqual("my-game", workspace.ProductId);
        }

        private static string CreateTempProject()
        {
            var root = Path.Combine(Path.GetTempPath(), "hydracept-unity-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Path.Combine(root, ".hydracept"));
            return root;
        }

        private static void WriteJson(string path, object payload)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, JsonSerializer.Serialize(payload));
        }
    }

    public sealed class ImportPreflightTests
    {
        [Test]
        public void SanitizeFileName_RemovesInvalidCharacters()
        {
            var sanitized = ImportPreflight.SanitizeFileName("bad<file>name.png");
            Assert.IsFalse(sanitized.Contains("<"));
        }

        [Test]
        public void ValidateBatch_RejectsPathsOutsideAssets()
        {
            var result = ImportPreflight.ValidateBatch(
                "Generated/Hydracept",
                new[] { ("art_1", "frame.png") });
            Assert.IsFalse(result.Success);
        }

        [Test]
        public void ValidateBatch_AcceptsCleanDestinations()
        {
            var result = ImportPreflight.ValidateBatch(
                "Assets/Generated/Hydracept/test-job",
                new[] { ("art_1", "frame.png"), ("art_2", "frame2.png") });
            Assert.IsTrue(result.Success);
            Assert.AreEqual(2, result.Destinations.Count);
        }
    }

    public sealed class JobCacheTests
    {
        [Test]
        public void Upsert_PersistsJobRecord()
        {
            var root = Path.Combine(Path.GetTempPath(), "hydracept-cache-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            JobCache.Upsert(root, "job_1", "image.generate.v1", "prompt", "running");
            var loaded = JobCache.Load(root);
            Assert.AreEqual(1, loaded.Jobs.Count);
            Assert.AreEqual("job_1", loaded.Jobs[0].JobId);
            Assert.AreEqual("prompt", loaded.Jobs[0].Prompt);
        }

        [Test]
        public void IsTerminal_DetectsTerminalStates()
        {
            Assert.IsTrue(JobCache.IsTerminal("succeeded"));
            Assert.IsTrue(JobCache.IsTerminal("failed"));
            Assert.IsFalse(JobCache.IsTerminal("running"));
        }
    }

    public sealed class ProvenanceWriterTests
    {
        [Test]
        public void Serialize_DoesNotContainSecrets()
        {
            var document = new ProvenanceDocument
            {
                JobId = "job_test",
                Capability = "image.generate.v1",
                ReceiptId = "rcpt_test",
            };
            var json = JsonSerializer.Serialize(document);
            Assert.IsFalse(json.Contains("apiKey"));
            Assert.IsFalse(json.Contains("Bearer"));
        }
    }
}
