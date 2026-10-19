# Framework MCP examples (hosted Hydracept)

Hosted MCP endpoint (compact default): `https://api.hydracept.com/mcp`  
Auth: `Authorization: Bearer $HYDRACEPT_API_KEY` (create at https://hydracept.com/start)

## One-click install (VS Code / Cursor)

Use the [MCP install deep link](./mcp-vscode-install.md) or copy `../mcp.hosted.vscode.json`.

## Examples

| Framework | Path |
|-----------|------|
| OpenAI Agents SDK | [openai-agents/](./openai-agents/) |
| Vercel AI SDK | [vercel-ai/](./vercel-ai/) |
| LangChain / LangGraph | [langchain/](./langchain/) |
| CrewAI | [crewai/](./crewai/) |
| Claude Agent SDK | [claude-agent-sdk/](./claude-agent-sdk/) |

Each folder is documentation-first with copy-paste configs. CI runs a live `GET /v1/capabilities` smoke when `HYDRACEPT_WOM_EXAMPLES_API_KEY` is configured in GitHub Actions (skipped otherwise).
