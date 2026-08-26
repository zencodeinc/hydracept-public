using System.Text.Json;

namespace Hydracept.Client;

/// <summary>Checkout identity from .hydracept/project.json. Open() never takes a project-id override.</summary>
public sealed class HydraceptWorkspace : IDisposable
{
    public HydraceptClient Client { get; }
    public HydraceptJobRunner Jobs { get; }
    public string Root { get; }

    private HydraceptWorkspace(HydraceptClient client, HydraceptJobRunner jobs, string root)
    {
        Client = client;
        Jobs = jobs;
        Root = root;
    }

    public static HydraceptWorkspace Open(string? root = null)
    {
        var projectRoot = Path.GetFullPath(root ?? Directory.GetCurrentDirectory());
        var bindingPath = Path.Combine(projectRoot, ".hydracept", "project.json");
        if (!File.Exists(bindingPath))
            throw new InvalidOperationException("Missing .hydracept/project.json — run python -m hydracept init");

        using var bindingDoc = JsonDocument.Parse(File.ReadAllText(bindingPath));
        var binding = bindingDoc.RootElement;
        var projectId = binding.GetProperty("projectId").GetString()
            ?? throw new InvalidOperationException("project.json is missing projectId");
        var envProject = Environment.GetEnvironmentVariable("HYDRACEPT_PROJECT")
            ?? Environment.GetEnvironmentVariable("HYDRACEPT_PROJECT_ID");
        if (!string.IsNullOrWhiteSpace(envProject) && envProject != projectId)
        {
            throw new InvalidOperationException(
                $"HYDRACEPT_PROJECT={envProject} disagrees with project.json projectId={projectId}");
        }

        var apiOrigin = "https://api.hydracept.com";
        if (binding.TryGetProperty("apiOrigin", out var originEl))
            apiOrigin = originEl.GetString() ?? apiOrigin;
        var environment = "development";
        if (binding.TryGetProperty("environment", out var envEl))
            environment = envEl.GetString() ?? environment;

        var secretsPath = Path.Combine(projectRoot, ".hydracept", "secrets.json");
        var token = Environment.GetEnvironmentVariable("HYDRACEPT_API_KEY");
        if (string.IsNullOrWhiteSpace(token) && File.Exists(secretsPath))
        {
            using var secretsDoc = JsonDocument.Parse(File.ReadAllText(secretsPath));
            if (secretsDoc.RootElement.TryGetProperty("apiKey", out var keyEl))
                token = keyEl.GetString();
            else if (secretsDoc.RootElement.TryGetProperty("token", out var tokEl))
                token = tokEl.GetString();
        }
        if (string.IsNullOrWhiteSpace(token))
            throw new InvalidOperationException("No workspace API key in secrets.json");

        var http = new HttpClient { BaseAddress = new Uri(apiOrigin.TrimEnd('/') + "/") };
        var client = new HydraceptClient(http, new HydraceptClientOptions
        {
            BaseUrl = apiOrigin,
            BearerToken = token,
        });
        var jobs = new HydraceptJobRunner(client, projectId, environment);
        return new HydraceptWorkspace(client, jobs, projectRoot);
    }

    public void Dispose()
    {
    }
}
