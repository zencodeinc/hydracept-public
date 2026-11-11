# Claude and Hydracept

## Directory connector

The Claude directory connector is `https://api.hydracept.com/mcp/claude`.

Claude signs the user in with OAuth. Do not set an `Authorization` header and do not send a Hydracept API key. This URL rejects API keys.

Setup: https://hydracept.com/claude/

## Claude Agent SDK custom server

A Claude Agent SDK process that cannot complete that browser sign-in can call the bearer hosted server. That server is not the directory connector:

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

Do not point that API key at `https://api.hydracept.com/mcp/claude`.
