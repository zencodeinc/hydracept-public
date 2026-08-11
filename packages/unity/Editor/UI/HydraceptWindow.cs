using System;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;
using Hydracept.Unity.Editor.Jobs;
using UnityEditor;
using UnityEditor.UIElements;
using UnityEngine;
using UnityEngine.UIElements;

namespace Hydracept.Unity.Editor.UI
{
    public sealed class HydraceptWindow : EditorWindow
    {
        private const string PackagePath = "Packages/com.hydracept.unity/Editor/UI/HydraceptWindow.uxml";
        private const string StylePath = "Packages/com.hydracept.unity/Editor/UI/HydraceptWindow.uss";

        private VisualElement _panelContainer = null!;
        private ToolbarToggle _tabGenerate = null!;
        private ToolbarToggle _tabSheet = null!;
        private ToolbarToggle _tabJobs = null!;
        private ToolbarToggle _tabStatus = null!;

        private StatusPanel? _statusPanel;
        private GenerateImagePanel? _generatePanel;
        private SheetSlicePanel? _sheetPanel;
        private JobsPanel? _jobsPanel;
        private JobPoller? _poller;
        private HydraceptJob? _trackedJob;
        private string _activeTab = "status";

        [MenuItem("Window/Hydracept")]
        public static void ShowWindow()
        {
            var window = GetWindow<HydraceptWindow>();
            window.titleContent = new GUIContent("Hydracept");
            window.Show();
        }

        public void CreateGUI()
        {
            var tree = AssetDatabase.LoadAssetAtPath<VisualTreeAsset>(PackagePath);
            var style = AssetDatabase.LoadAssetAtPath<StyleSheet>(StylePath);
            if (tree == null)
            {
                rootVisualElement.Add(new Label("Hydracept UI assets missing."));
                return;
            }

            tree.CloneTree(rootVisualElement);
            if (style != null)
            {
                rootVisualElement.styleSheets.Add(style);
            }

            _panelContainer = rootVisualElement.Q<ScrollView>("panel-container");
            _tabGenerate = rootVisualElement.Q<ToolbarToggle>("tab-generate");
            _tabSheet = rootVisualElement.Q<ToolbarToggle>("tab-sheet");
            _tabJobs = rootVisualElement.Q<ToolbarToggle>("tab-jobs");
            _tabStatus = rootVisualElement.Q<ToolbarToggle>("tab-status");

            _tabGenerate.RegisterValueChangedCallback(evt => { if (evt.newValue) ShowTab("generate"); });
            _tabSheet.RegisterValueChangedCallback(evt => { if (evt.newValue) ShowTab("sheet"); });
            _tabJobs.RegisterValueChangedCallback(evt => { if (evt.newValue) ShowTab("jobs"); });
            _tabStatus.RegisterValueChangedCallback(evt => { if (evt.newValue) ShowTab("status"); });

            _statusPanel = new StatusPanel(CreatePanelRoot());
            _generatePanel = new GenerateImagePanel(CreatePanelRoot(), OnJobSubmitted);
            _sheetPanel = new SheetSlicePanel(CreatePanelRoot(), OnJobSubmitted);
            _jobsPanel = new JobsPanel(CreatePanelRoot());

            _tabStatus.value = true;
            ShowTab("status");
            InitializePoller();
        }

        private void OnEnable()
        {
            InitializePoller();
            RestoreTrackedJobFromCache();
        }

        private void RestoreTrackedJobFromCache()
        {
            var root = WorkspaceLocator.FindProjectRoot();
            if (root == null || _trackedJob != null)
            {
                return;
            }

            foreach (var cached in JobCache.NonTerminalJobs(root))
            {
                _trackedJob = new HydraceptJob
                {
                    JobId = cached.JobId,
                    CapabilityKey = cached.CapabilityKey,
                    Status = cached.Status,
                };
                _poller?.Track(cached.JobId);
                break;
            }
        }

        private void OnDisable()
        {
            _poller?.Stop();
        }

        public void RefreshStatus()
        {
            ShowTab("status");
        }

        private VisualElement CreatePanelRoot() => new VisualElement();

        private void ShowTab(string tab)
        {
            _activeTab = tab;
            _tabGenerate.SetValueWithoutNotify(tab == "generate");
            _tabSheet.SetValueWithoutNotify(tab == "sheet");
            _tabJobs.SetValueWithoutNotify(tab == "jobs");
            _tabStatus.SetValueWithoutNotify(tab == "status");

            _panelContainer.Clear();
            switch (tab)
            {
                case "generate":
                    _generatePanel = new GenerateImagePanel(_panelContainer, OnJobSubmitted);
                    _generatePanel.SetJob(_trackedJob);
                    break;
                case "sheet":
                    _sheetPanel = new SheetSlicePanel(_panelContainer, OnJobSubmitted);
                    _sheetPanel.SetJob(_trackedJob);
                    break;
                case "jobs":
                    _jobsPanel = new JobsPanel(_panelContainer);
                    _ = _jobsPanel.RefreshAsync();
                    break;
                default:
                    _statusPanel = new StatusPanel(_panelContainer);
                    _ = _statusPanel.RefreshAsync();
                    break;
            }
        }

        private void InitializePoller()
        {
            var root = WorkspaceLocator.FindProjectRoot();
            var client = HydraceptConnection.CreateClient();
            if (root == null || client == null)
            {
                return;
            }

            _poller ??= new JobPoller(client, root);
            _poller.JobUpdated -= OnJobUpdated;
            _poller.JobCompleted -= OnJobCompleted;
            _poller.JobUpdated += OnJobUpdated;
            _poller.JobCompleted += OnJobCompleted;
            _poller.ReconcileNonTerminalJobs();
        }

        private void OnJobSubmitted(HydraceptJob job)
        {
            _trackedJob = job;
            _poller?.Track(job.JobId);
        }

        private void OnJobUpdated(HydraceptJob job)
        {
            _trackedJob = job;
            if (_activeTab == "generate")
            {
                _generatePanel?.SetJob(job);
            }
            else if (_activeTab == "sheet")
            {
                _sheetPanel?.SetJob(job);
            }
        }

        private void OnJobCompleted(HydraceptJob job)
        {
            OnJobUpdated(job);
            Repaint();
        }
    }
}
