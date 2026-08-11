using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;

namespace Hydracept.Unity.Editor.Auth
{
    public sealed class ResolvedWorkspace
    {
        public string ApiUrl { get; set; } = "https://api.hydracept.com";
        public string Token { get; set; } = string.Empty;
        public string ProjectId { get; set; } = string.Empty;
        public string Environment { get; set; } = "development";
        public string ProductId { get; set; } = string.Empty;
        public string ProjectName { get; set; } = string.Empty;
        public WorkspaceState State { get; set; } = WorkspaceState.Unconfigured;
    }

    public static class WorkspaceReader
    {
        private const string DefaultApi = "https://api.hydracept.com";

        public static ResolvedWorkspace Resolve(string? projectRoot)
        {
            if (string.IsNullOrWhiteSpace(projectRoot))
            {
                return new ResolvedWorkspace { State = WorkspaceState.Unconfigured };
            }

            var config = ReadJson(Path.Combine(projectRoot, ".hydracept", "config.json"));
            var secrets = ReadJson(Path.Combine(projectRoot, ".hydracept", "secrets.json"));

            var token = FirstNonEmpty(
                EnvironmentValue("HYDRACEPT_API_KEY"),
                EnvironmentValue("HYDRACEPT_TOKEN"),
                secrets?["apiKey"]?.ToString(),
                secrets?["token"]?.ToString());

            if (string.IsNullOrWhiteSpace(token))
            {
                return new ResolvedWorkspace { State = WorkspaceState.Unconfigured };
            }

            var apiUrl = FirstNonEmpty(
                EnvironmentValue("HYDRACEPT_API_URL"),
                config?["apiBaseUrl"]?.ToString(),
                DefaultApi)!.TrimEnd('/');

            var projectId = FirstNonEmpty(
                EnvironmentValue("HYDRACEPT_PROJECT"),
                config?["projectId"]?.ToString()) ?? string.Empty;

            var environment = FirstNonEmpty(
                EnvironmentValue("HYDRACEPT_ENVIRONMENT"),
                config?["environment"]?.ToString(),
                "development")!;

            var productId = FirstNonEmpty(
                config?["productId"]?.ToString(),
                projectId) ?? string.Empty;

            var projectName = config?["projectName"]?.ToString() ?? string.Empty;

            var state = string.IsNullOrWhiteSpace(projectId)
                ? WorkspaceState.Authenticated
                : WorkspaceState.Ready;

            return new ResolvedWorkspace
            {
                ApiUrl = apiUrl,
                Token = token,
                ProjectId = projectId,
                Environment = environment,
                ProductId = productId,
                ProjectName = projectName,
                State = state,
            };
        }

        private static JObject? ReadJson(string path)
        {
            if (!File.Exists(path))
            {
                return null;
            }

            return JObject.Parse(File.ReadAllText(path));
        }

        private static string? EnvironmentValue(string name)
        {
            var value = Environment.GetEnvironmentVariable(name);
            return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        }

        private static string? FirstNonEmpty(params string?[] values)
        {
            foreach (var value in values)
            {
                if (!string.IsNullOrWhiteSpace(value))
                {
                    return value.Trim();
                }
            }

            return null;
        }
    }
}
