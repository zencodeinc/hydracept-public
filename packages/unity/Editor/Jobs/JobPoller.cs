using System;
using System.Threading;
using System.Threading.Tasks;
using Hydracept.Unity.Editor.Api;
using Hydracept.Unity.Editor.Api.Generated;
using Hydracept.Unity.Editor.Auth;
using UnityEditor;

namespace Hydracept.Unity.Editor.Jobs
{
    public sealed class JobPoller
    {
        private readonly HydraceptApiClient _client;
        private readonly string _projectRoot;
        private string? _activeJobId;
        private EditorApplication.CallbackFunction? _updateHandler;

        public event Action<HydraceptJob>? JobUpdated;
        public event Action<HydraceptJob>? JobCompleted;

        public JobPoller(HydraceptApiClient client, string projectRoot)
        {
            _client = client;
            _projectRoot = projectRoot;
        }

        public void Track(string jobId)
        {
            _activeJobId = jobId;
            EnsureHook();
        }

        public void ReconcileNonTerminalJobs()
        {
            foreach (var cached in JobCache.NonTerminalJobs(_projectRoot))
            {
                _ = PollOnceAsync(cached.JobId);
            }
        }

        public void Stop()
        {
            if (_updateHandler != null)
            {
                EditorApplication.update -= _updateHandler;
                _updateHandler = null;
            }
        }

        private void EnsureHook()
        {
            if (_updateHandler != null)
            {
                return;
            }

            _updateHandler = OnEditorUpdate;
            EditorApplication.update += _updateHandler;
        }

        private void OnEditorUpdate()
        {
            if (string.IsNullOrWhiteSpace(_activeJobId))
            {
                return;
            }

            var jobId = _activeJobId;
            _activeJobId = null;
            _ = PollOnceAsync(jobId);
        }

        private async Task PollOnceAsync(string jobId)
        {
            try
            {
                var job = await _client.GetJobAsync(jobId, CancellationToken.None);
                JobCache.UpdateStatus(_projectRoot, job.JobId, job.Status);
                JobUpdated?.Invoke(job);
                if (JobCache.IsTerminal(job.Status))
                {
                    JobCompleted?.Invoke(job);
                    return;
                }

                _activeJobId = jobId;
            }
            catch (Exception)
            {
                _activeJobId = jobId;
            }
        }
    }
}
