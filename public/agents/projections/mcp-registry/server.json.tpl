{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "{{registryName}}",
  "title": "{{displayName}}",
  "description": "{{registryDescription}}",
  "version": "{{distributionVersion}}",
  "websiteUrl": "{{pluginHomepage}}",
  "repository": {
    "url": "https://github.com/zencodeinc/hydracept-agent-plugins",
    "source": "github"
  },
  "remotes": [
    {
      "type": "streamable-http",
      "url": "{{hostedMcpUrl}}"
    }
  ]
}
