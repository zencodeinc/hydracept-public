# Claude Agent SDK + Hydracept hosted MCP

Add to your Claude Agent project `mcp.json` / SDK config:

```json
{
  "mcpServers": {
    "hydracept": {
      "type": "http",
      "url": "https://api.hydracept.com/mcp",
      "headers": {
        "Authorization": "Bearer ${HYDRACEPT_API_KEY}"
      }
    }
  }
}
```

OAuth-only Claude Directory surface (`/mcp/claude`) is separate from this bearer-hosted path.
