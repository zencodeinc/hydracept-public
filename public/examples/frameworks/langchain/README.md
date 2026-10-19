# LangChain / LangGraph + Hydracept hosted MCP

Use `langchain-mcp-adapters` with streamable HTTP:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient(
    {
        "hydracept": {
            "transport": "streamable_http",
            "url": "https://api.hydracept.com/mcp",
            "headers": {"Authorization": f"Bearer {os.environ['HYDRACEPT_API_KEY']}"},
        }
    }
)
tools = await client.get_tools()
```

Graph agents: pass tools into your LangGraph tool node as usual.
