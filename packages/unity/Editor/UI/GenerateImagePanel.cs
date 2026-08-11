using System;
using System.Collections.Generic;
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
    public sealed class GenerateImagePanel
    {
        private readonly VisualElement _root;
        private readonly Action<HydraceptJob> _onJobSubmitted;
        private TextField _prompt = null!;
        private IntegerField _width = null!;
        private IntegerField _height = null!;
        private IntegerField _variants = null!;
        private Toggle _transparent = null!;
        private EnumField _profile = null!;
        private TextField _destination = null!;
        private Label _status = null!;
        private HydraceptJob? _activeJob;

        public GenerateImagePanel(VisualElement root, Action<HydraceptJob> onJobSubmitted)
        {
            _root = root;
            _onJobSubmitted = onJobSubmitted;
            Build();
        }

        private void Build()
        {
            _root.Clear();
            _prompt = new TextField("Prompt") { multiline = true };
            _width = new IntegerField("Width") { value = 512 };
            _height = new IntegerField("Height") { value = 512 };
            _variants = new IntegerField("Variants") { value = 1 };
            _transparent = new Toggle("Transparent Output") { value = true };
            _profile = new EnumField("Import Profile", ImageImportProfileKind.Sprite);
            _destination = new TextField("Destination Folder")
            {
                value = "Assets/Generated/Hydracept",
            };
            _status = new Label();

            var generate = new Button(OnGenerateClicked) { text = "Generate" };
            _root.Add(_prompt);
            _root.Add(_width);
            _root.Add(_height);
            _root.Add(_variants);
            _root.Add(_transparent);
            _root.Add(_profile);
            _root.Add(_destination);
            _root.Add(generate);
            _root.Add(_status);
        }

        public void SetJob(HydraceptJob? job)
        {
            _activeJob = job;
            if (job == null)
            {
                return;
            }

            _status.text = $"Job: {job.JobId} — Status: {job.Status}";
            if (!JobCache.IsTerminal(job.Status))
            {
                return;
            }

            foreach (var artifact in job.Artifacts)
            {
                var row = new VisualElement();
                row.AddToClassList("hydracept-row");
                row.Add(new Label($"Variant {artifact.VariantIndex ?? 0} — {artifact.ArtifactId}"));
                row.Add(new Button(() => PreviewArtifact(job, artifact)) { text = "Preview" });
                row.Add(new Button(() => ImportArtifact(job, artifact)) { text = "Import" });
                _root.Add(row);
            }

            if (job.Artifacts.Count > 1)
            {
                _root.Add(new Button(() => ImportAll(job)) { text = "Import All" });
            }

            if (!string.IsNullOrWhiteSpace(job.ReceiptId))
            {
                var receiptBox = new VisualElement();
                ReceiptPanel.Render(receiptBox, job, receipt: null);
                _root.Add(receiptBox);
            }
        }

        private async void PreviewArtifact(HydraceptJob job, HydraceptJobArtifactRef artifact)
        {
            var client = HydraceptConnection.CreateClient();
            if (client == null)
            {
                return;
            }

            var tempPath = await ArtifactDownloader.DownloadToTempAsync(
                client,
                job.JobId,
                artifact.ArtifactId,
                $"{artifact.ArtifactId}.png");
            EditorUtility.RevealInFinder(tempPath);
        }

        private async void OnGenerateClicked()
        {
            var root = WorkspaceLocator.FindProjectRoot();
            var workspace = WorkspaceReader.Resolve(root);
            var client = HydraceptConnection.CreateClient();
            if (root == null || client == null || workspace.State != WorkspaceState.Ready)
            {
                _status.text = "Workspace not ready.";
                return;
            }

            var service = new JobService(client, workspace, root);
            var input = new Dictionary<string, object>
            {
                ["prompt"] = _prompt.value,
                ["width"] = _width.value,
                ["height"] = _height.value,
                ["variantCount"] = Math.Clamp(_variants.value, 1, 4),
                ["requestTransparentOutput"] = _transparent.value,
            };

            try
            {
                var job = await service.SubmitAsync("image.generate.v1", input, _prompt.value);
                _status.text = $"Submitted — Job: {job.JobId}";
                _onJobSubmitted(job);
            }
            catch (Exception ex)
            {
                _status.text = ex.Message;
            }
        }

        private async void ImportArtifact(HydraceptJob job, HydraceptJobArtifactRef artifact)
        {
            var client = HydraceptConnection.CreateClient();
            if (client == null)
            {
                return;
            }

            var options = BuildOptions(job);
            var result = await ArtifactImporter.ImportSingleAsync(client, job, artifact, options);
            _status.text = result.Success
                ? $"Imported {artifact.ArtifactId}"
                : result.Error ?? "Import failed";
        }

        private async void ImportAll(HydraceptJob job)
        {
            var client = HydraceptConnection.CreateClient();
            if (client == null)
            {
                return;
            }

            var result = await ArtifactImporter.ImportAllAsync(client, job, BuildOptions(job));
            _status.text = result.Success
                ? $"Imported {result.ImportedAssetPaths.Count} assets"
                : result.Error ?? "Import failed";
        }

        private ArtifactImportOptions BuildOptions(HydraceptJob job)
        {
            return new ArtifactImportOptions
            {
                DestinationRoot = _destination.value,
                Profile = (ImageImportProfileKind)_profile.value,
                CapabilityKey = job.CapabilityKey,
                ReceiptId = job.ReceiptId,
            };
        }
    }
}
