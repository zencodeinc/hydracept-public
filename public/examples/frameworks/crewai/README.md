# CrewAI + Hydracept hosted MCP

```python
from crewai_tools import MCPServerAdapter

server_params = {
    "url": "https://api.hydracept.com/mcp",
    "transport": "streamable-http",
    "headers": {"Authorization": f"Bearer {os.environ['HYDRACEPT_API_KEY']}"},
}

with MCPServerAdapter(server_params) as tools:
    # attach `tools` to an Agent
    ...
```

See CrewAI MCP docs for adapter version requirements.
