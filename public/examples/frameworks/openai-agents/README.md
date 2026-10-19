# OpenAI Agents SDK + Hydracept hosted MCP

Use the Agents SDK MCP integration with streamable HTTP:

```python
# Pseudocode — see https://openai.github.io/openai-agents-python/mcp/
from agents.mcp import MCPServerStreamableHttp

hydracept = MCPServerStreamableHttp(
    name="hydracept",
    url="https://api.hydracept.com/mcp",
    headers={"Authorization": f"Bearer {os.environ['HYDRACEPT_API_KEY']}"},
)
# Pass `mcp_servers=[hydracept]` to your Agent/runner.
```

Requires `HYDRACEPT_API_KEY`. Full tool surface: `https://api.hydracept.com/mcp/full`.
