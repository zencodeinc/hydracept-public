using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Import;
using Hydracept.Unity.Editor.Jobs;
using UnityEngine.UIElements;

namespace Hydracept.Unity.Editor.UI
{
    public sealed class SheetSlicePanel
    {
        private readonly VisualElement _root;
        private readonly Action<HydraceptJob> _onJobSubmitted;
        private TextField _prompt = null!;
        private IntegerField _columns = null!;
        private IntegerField _rows = null!;
        private IntegerField _frameWidth = null!;
        private IntegerField _frameHeight = null!;
        private Toggle _transparent = null!;
        private TextField _destination = null!;
        private Label _status = null!;

        public SheetSlicePanel(VisualElement root, Action<HydraceptJob> onJobSubmitted)
        {
            _root = root;
            _onJobSubmitted = onJobSubmitted;
            Build();
        }

        private void Build()
        {
            _root.Clear();
            _prompt = new TextField("Prompt") { multiline = true };
            _columns = new IntegerField("Columns") { value = 2 };
            _rows = new IntegerField("Rows") { value = 2 };
            _frameWidth = new IntegerField("Frame Width") { value = 512 };
            _frameHeight = new IntegerField("Frame Height") { value = 512 };
            _transparent = new Toggle("Transparent background") { value = true };
            _destination = new TextField("Destination")
            {
                value = "Assets/Generated/Hydracept",
            };
            _status = new Label();
            _root.Add(new Label(
                "Hydracept generates items together, isolates each item, slices them, and centers normalized frames."));
            _root.Add(_prompt);
            _root.Add(_columns);
            _root.Add(_rows);
            _root.Add(_frameWidth);
            _root.Add(_frameHeight);
            _root.Add(_transparent);
            _root.Add(_destination);
            _root.Add(new Button(OnGenerateClicked) { text = "Generate Sheet" });
            _root.Add(_status);
        }

        public void SetJob(HydraceptJob? job)
        {
            if (job == null)
            {
                return;
            }

            _status.text = $"Generated {job.Artifacts.Count} slices — {job.Status}";
            if (!JobCache.IsTerminal(job.Status) || job.Artifacts.Count == 0)
            {
                return;
            }

            _root.Add(new Button(() => ImportAll(job)) { text = "Import All" });
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

            var labels = new List<object>();
            var total = Math.Max(1, _columns.value) * Math.Max(1, _rows.value);
            for (var i = 1; i <= total; i++)
            {
                labels.Add($"frame-{i:00}");
            }

            var input = new Dictionary<string, object>
            {
                ["prompt"] = _prompt.value,
                ["requestTransparentOutput"] = _transparent.value,
                ["variantCount"] = 1,
                ["sheet"] = new Dictionary<string, object>
                {
                    ["rows"] = _rows.value,
                    ["columns"] = _columns.value,
                    ["slice"] = true,
                    ["labels"] = labels,
                    ["normalize"] = new Dictionary<string, object>
                    {
                        ["width"] = _frameWidth.value,
                        ["height"] = _frameHeight.value,
                        ["center"] = true,
                    },
                },
            };

            try
            {
                var service = new JobService(client, workspace, root);
                var job = await service.SubmitAsync("image.generate.v1", input, _prompt.value);
                _status.text = $"Submitted — Job: {job.JobId}";
                _onJobSubmitted(job);
            }
            catch (Exception ex)
            {
                _status.text = ex.Message;
            }
        }

        private async void ImportAll(HydraceptJob job)
        {
            var client = HydraceptConnection.CreateClient();
            if (client == null)
            {
                return;
            }

            var options = new ArtifactImportOptions
            {
                DestinationRoot = _destination.value,
                Profile = ImageImportProfileKind.Sprite,
                CapabilityKey = job.CapabilityKey,
                ReceiptId = job.ReceiptId,
            };
            var result = await ArtifactImporter.ImportAllAsync(client, job, options);
            _status.text = result.Success
                ? $"Imported {result.ImportedAssetPaths.Count} sprites"
                : result.Error ?? "Import failed";
        }
    }
}
