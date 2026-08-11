using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Hydracept.Unity.Editor.Jobs
{
    public sealed class CachedJobRecord
    {
        [JsonProperty("jobId")]
        public string JobId = string.Empty;

        [JsonProperty("capabilityKey")]
        public string CapabilityKey = string.Empty;

        [JsonProperty("submittedAt")]
        public string SubmittedAt = string.Empty;

        [JsonProperty("prompt")]
        public string? Prompt;

        [JsonProperty("status")]
        public string Status = "queued";
    }

    public sealed class JobCacheDocument
    {
        [JsonProperty("schemaVersion")]
        public string SchemaVersion = "hydracept.unity.recent-jobs.v1";

        [JsonProperty("jobs")]
        public List<CachedJobRecord> Jobs = new();
    }

    public static class JobCache
    {
        public static string CachePath(string projectRoot) =>
            Path.Combine(projectRoot, ".hydracept", "unity-recent-jobs.json");

        public static JobCacheDocument Load(string projectRoot)
        {
            var path = CachePath(projectRoot);
            if (!File.Exists(path))
            {
                return new JobCacheDocument();
            }

            return JsonConvert.DeserializeObject<JobCacheDocument>(File.ReadAllText(path))
                ?? new JobCacheDocument();
        }

        public static void Save(string projectRoot, JobCacheDocument document)
        {
            var path = CachePath(projectRoot);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, JsonConvert.SerializeObject(document, Formatting.Indented));
        }

        public static void Upsert(
            string projectRoot,
            string jobId,
            string capabilityKey,
            string? prompt,
            string status)
        {
            var document = Load(projectRoot);
            var existing = document.Jobs.Find(job => job.JobId == jobId);
            if (existing == null)
            {
                existing = new CachedJobRecord
                {
                    JobId = jobId,
                    CapabilityKey = capabilityKey,
                    SubmittedAt = DateTime.UtcNow.ToString("o"),
                    Prompt = prompt,
                    Status = status,
                };
                document.Jobs.Insert(0, existing);
            }
            else
            {
                existing.CapabilityKey = capabilityKey;
                existing.Prompt = prompt ?? existing.Prompt;
                existing.Status = status;
            }

            if (document.Jobs.Count > 200)
            {
                document.Jobs.RemoveRange(200, document.Jobs.Count - 200);
            }

            Save(projectRoot, document);
        }

        public static void UpdateStatus(string projectRoot, string jobId, string status)
        {
            var document = Load(projectRoot);
            var existing = document.Jobs.Find(job => job.JobId == jobId);
            if (existing == null)
            {
                return;
            }

            existing.Status = status;
            Save(projectRoot, document);
        }

        public static IEnumerable<CachedJobRecord> NonTerminalJobs(string projectRoot)
        {
            foreach (var job in Load(projectRoot).Jobs)
            {
                if (!IsTerminal(job.Status))
                {
                    yield return job;
                }
            }
        }

        public static bool IsTerminal(string status)
        {
            var normalized = (status ?? string.Empty).ToLowerInvariant();
            return normalized is "succeeded" or "failed" or "canceled" or "cancelled";
        }
    }
}
