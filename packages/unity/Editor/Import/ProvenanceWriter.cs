using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using UnityEditor;
using UnityEngine;

namespace Hydracept.Unity.Editor.Import
{
    public sealed class ProvenanceArtifact
    {
        [JsonProperty("artifactId")]
        public string ArtifactId = string.Empty;

        [JsonProperty("sha256")]
        public string? Sha256;

        [JsonProperty("path")]
        public string Path = string.Empty;
    }

    public sealed class ProvenanceDocument
    {
        [JsonProperty("schemaVersion")]
        public string SchemaVersion = "hydracept.unity.provenance.v1";

        [JsonProperty("jobId")]
        public string JobId = string.Empty;

        [JsonProperty("capability")]
        public string Capability = string.Empty;

        [JsonProperty("receiptId")]
        public string? ReceiptId;

        [JsonProperty("artifacts")]
        public List<ProvenanceArtifact> Artifacts = new();
    }

    public static class ProvenanceWriter
    {
        public static string Write(
            string destinationRoot,
            ProvenanceDocument document)
        {
            var path = $"{destinationRoot.TrimEnd('/')}/hydracept.provenance.json".Replace('\\', '/');
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            var json = JsonConvert.SerializeObject(document, Formatting.Indented);
            File.WriteAllText(path, json);
            AssetDatabase.ImportAsset(path);
            return path;
        }
    }
}
