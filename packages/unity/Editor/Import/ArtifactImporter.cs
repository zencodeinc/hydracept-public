using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;
using UnityEditor;
using UnityEngine;

namespace Hydracept.Unity.Editor.Import
{
    public sealed class ArtifactImportOptions
    {
        public string DestinationRoot = "Assets/Generated/Hydracept";
        public ImageImportProfileKind Profile = ImageImportProfileKind.Sprite;
        public string CapabilityKey = "image.generate.v1";
        public string? ReceiptId;
    }

    public sealed class ArtifactImportResult
    {
        public bool Success { get; set; }
        public string? Error { get; set; }
        public List<string> ImportedAssetPaths { get; set; } = new();
        public string? ProvenancePath { get; set; }
    }

    public static class ArtifactImporter
    {
        public static async Task<ArtifactImportResult> ImportSingleAsync(
            HydraceptApiClient client,
            HydraceptJob job,
            HydraceptJobArtifactRef artifact,
            ArtifactImportOptions options,
            CancellationToken cancellationToken = default)
        {
            var jobFolder = $"{options.DestinationRoot.TrimEnd('/')}/{options.CapabilityKey}/{job.JobId}";
            var fileName = $"{artifact.ArtifactId}.png";
            var preflight = ImportPreflight.ValidateBatch(
                jobFolder,
                new[] { (artifact.ArtifactId, fileName) });
            if (!preflight.Success)
            {
                return new ArtifactImportResult { Success = false, Error = preflight.Error };
            }

            return await ImportValidatedAsync(client, job, preflight.Destinations, options, cancellationToken);
        }

        public static async Task<ArtifactImportResult> ImportAllAsync(
            HydraceptApiClient client,
            HydraceptJob job,
            ArtifactImportOptions options,
            CancellationToken cancellationToken = default)
        {
            var jobFolder = $"{options.DestinationRoot.TrimEnd('/')}/{options.CapabilityKey}/{job.JobId}";
            var artifacts = new List<(string artifactId, string fileName)>();
            var index = 1;
            foreach (var artifact in job.Artifacts)
            {
                var label = $"{index:00}_{artifact.ArtifactId}.png";
                artifacts.Add((artifact.ArtifactId, label));
                index++;
            }

            var preflight = ImportPreflight.ValidateBatch(jobFolder, artifacts);
            if (!preflight.Success)
            {
                return new ArtifactImportResult { Success = false, Error = preflight.Error };
            }

            return await ImportValidatedAsync(client, job, preflight.Destinations, options, cancellationToken);
        }

        private static async Task<ArtifactImportResult> ImportValidatedAsync(
            HydraceptApiClient client,
            HydraceptJob job,
            List<ImportDestination> destinations,
            ArtifactImportOptions options,
            CancellationToken cancellationToken)
        {
            var imported = new List<string>();
            var provenanceArtifacts = new List<ProvenanceArtifact>();

            foreach (var destination in destinations)
            {
                var tempPath = await ArtifactDownloader.DownloadToTempAsync(
                    client,
                    job.JobId,
                    destination.ArtifactId,
                    destination.FileName,
                    cancellationToken);

                var directory = Path.GetDirectoryName(destination.AssetPath);
                if (!string.IsNullOrWhiteSpace(directory))
                {
                    Directory.CreateDirectory(directory);
                }

                File.Copy(tempPath, destination.AssetPath, overwrite: false);
                AssetDatabase.ImportAsset(destination.AssetPath);
                ApplyImportProfile(destination.AssetPath, options.Profile);
                imported.Add(destination.AssetPath);
                provenanceArtifacts.Add(new ProvenanceArtifact
                {
                    ArtifactId = destination.ArtifactId,
                    Path = destination.AssetPath,
                });
            }

            var provenance = new ProvenanceDocument
            {
                JobId = job.JobId,
                Capability = options.CapabilityKey,
                ReceiptId = options.ReceiptId ?? job.ReceiptId,
                Artifacts = provenanceArtifacts,
            };
            var provenancePath = ProvenanceWriter.Write(
                $"{options.DestinationRoot.TrimEnd('/')}/{options.CapabilityKey}/{job.JobId}",
                provenance);

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            return new ArtifactImportResult
            {
                Success = true,
                ImportedAssetPaths = imported,
                ProvenancePath = provenancePath,
            };
        }

        public static void ApplyImportProfile(string assetPath, ImageImportProfileKind profile)
        {
            var importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
            if (importer == null)
            {
                return;
            }

            switch (profile)
            {
                case ImageImportProfileKind.Sprite:
                    importer.textureType = TextureImporterType.Sprite;
                    importer.alphaIsTransparency = true;
                    importer.spriteImportMode = SpriteImportMode.Single;
                    importer.mipmapEnabled = false;
                    break;
                case ImageImportProfileKind.PixelArtSprite:
                    importer.textureType = TextureImporterType.Sprite;
                    importer.filterMode = FilterMode.Point;
                    importer.mipmapEnabled = false;
                    importer.textureCompression = TextureImporterCompression.Uncompressed;
                    break;
                case ImageImportProfileKind.UiSprite:
                    importer.textureType = TextureImporterType.Sprite;
                    importer.alphaIsTransparency = true;
                    importer.mipmapEnabled = false;
                    break;
                case ImageImportProfileKind.Texture:
                    break;
            }

            importer.SaveAndReimport();
        }
    }
}
