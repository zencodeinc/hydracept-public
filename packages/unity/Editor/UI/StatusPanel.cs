using System.Threading.Tasks;
using Hydracept.Unity.Editor.Auth;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

namespace Hydracept.Unity.Editor.UI
{
    public sealed class StatusPanel
    {
        private readonly VisualElement _root;

        public StatusPanel(VisualElement root)
        {
            _root = root;
        }

        public async Task RefreshAsync()
        {
            _root.Clear();
            var actions = new VisualElement();
            actions.AddToClassList("hydracept-row");
            actions.Add(new Button(() => _ = RefreshAsync()) { text = "Refresh" });
            actions.Add(new Button(() => Application.OpenURL("https://docs.hydracept.com/unity-integration"))
            {
                text = "Open Docs",
            });
            _root.Add(actions);

            var status = await HydraceptConnection.GetStatusAsync();
            _root.Add(new Label($"API: {(status.State == WorkspaceState.Ready ? "Connected" : "Not configured")}"));
            _root.Add(new Label($"Workspace: {FormatWorkspaceState(status.State)}"));
            _root.Add(new Label($"Project: {status.ProjectName ?? status.ProjectId}"));
            _root.Add(new Label($"Environment: {status.Environment}"));

            if (status.State != WorkspaceState.Ready)
            {
                _root.Add(new Label("Run: python -m hydracept quickstart --token <HYDRACEPT_API_KEY> --json"));
                var setup = new Button(() => Application.OpenURL("https://hydracept.com/start"))
                {
                    text = "Open Hydracept Setup",
                };
                _root.Add(setup);
                return;
            }

            _root.Add(new Label("Capabilities"));
            foreach (var capability in status.Capabilities)
            {
                _root.Add(new Label($"✓ {capability}"));
            }

            if (!string.IsNullOrWhiteSpace(status.Error))
            {
                var error = new Label(status.Error) { name = "status-error" };
                error.AddToClassList("hydracept-error");
                _root.Add(error);
            }
        }

        private static string FormatWorkspaceState(WorkspaceState state) =>
            state switch
            {
                WorkspaceState.Ready => "Ready",
                WorkspaceState.Authenticated => "Authentication required",
                _ => "Not configured",
            };
    }
}
