using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace Hydracept.Unity.Editor.Import
{
    public sealed class ImportDestination
    {
        public string ArtifactId = string.Empty;
        public string FileName = string.Empty;
        public string AssetPath = string.Empty;
    }

    public sealed class ImportPreflightResult
    {
        public bool Success { get; set; }
        public string? Error { get; set; }
        public List<ImportDestination> Destinations { get; set; } = new();
    }

    public static class ImportPreflight
    {
        private static readonly Regex InvalidChars = new(@"[<>:""/\\|?*\x00-\x1F]", RegexOptions.Compiled);

        public static ImportPreflightResult ValidateBatch(
            string destinationRoot,
            IEnumerable<(string artifactId, string fileName)> artifacts)
        {
            var normalizedRoot = NormalizeAssetsRoot(destinationRoot);
            if (normalizedRoot == null)
            {
                return new ImportPreflightResult
                {
                    Success = false,
                    Error = "Destination must be under Assets/.",
                };
            }

            var destinations = new List<ImportDestination>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            foreach (var (artifactId, fileName) in artifacts)
            {
                var safeName = SanitizeFileName(fileName);
                if (string.IsNullOrWhiteSpace(safeName))
                {
                    return new ImportPreflightResult
                    {
                        Success = false,
                        Error = $"Invalid filename for artifact {artifactId}.",
                    };
                }

                var assetPath = $"{normalizedRoot}/{safeName}".Replace('\\', '/');
                if (!assetPath.StartsWith("Assets/", StringComparison.Ordinal))
                {
                    return new ImportPreflightResult
                    {
                        Success = false,
                        Error = $"Resolved path escapes Assets/: {assetPath}",
                    };
                }

                if (!seen.Add(assetPath))
                {
                    return new ImportPreflightResult
                    {
                        Success = false,
                        Error = $"Duplicate destination in batch: {assetPath}",
                    };
                }

                if (File.Exists(assetPath) || AssetDatabase.LoadMainAssetAtPath(assetPath) != null)
                {
                    return new ImportPreflightResult
                    {
                        Success = false,
                        Error = $"Asset already exists: {assetPath}",
                    };
                }

                destinations.Add(new ImportDestination
                {
                    ArtifactId = artifactId,
                    FileName = safeName,
                    AssetPath = assetPath,
                });
            }

            return new ImportPreflightResult
            {
                Success = true,
                Destinations = destinations,
            };
        }

        public static string? NormalizeAssetsRoot(string destinationRoot)
        {
            var trimmed = (destinationRoot ?? string.Empty).Trim().Replace('\\', '/');
            if (string.IsNullOrWhiteSpace(trimmed))
            {
                trimmed = "Assets/Generated/Hydracept";
            }

            if (!trimmed.StartsWith("Assets/", StringComparison.Ordinal))
            {
                if (trimmed == "Assets")
                {
                    trimmed = "Assets/Generated/Hydracept";
                }
                else
                {
                    return null;
                }
            }

            return trimmed.TrimEnd('/');
        }

        public static string SanitizeFileName(string fileName)
        {
            var name = (fileName ?? string.Empty).Replace('\\', '/').Trim();
            var slash = name.LastIndexOf('/');
            if (slash >= 0)
            {
                name = name[(slash + 1)..];
            }

            name = InvalidChars.Replace(name, "_");
            return name.Trim();
        }
    }
}
