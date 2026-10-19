# Vercel AI SDK + Hydracept hosted MCP

```typescript
import { experimental_createMCPClient } from "ai";

const client = await experimental_createMCPClient({
  transport: {
    type: "http",
    url: "https://api.hydracept.com/mcp",
    headers: { Authorization: `Bearer ${process.env.HYDRACEPT_API_KEY}` },
  },
});
const tools = await client.tools();
```

Set `HYDRACEPT_API_KEY` in your deployment env. See https://sdk.vercel.ai/docs/ai-sdk-core/mcp-tools.
