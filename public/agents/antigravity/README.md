# Hydracept for Antigravity

Hydracept is an execution control plane for agents: discover capabilities, quote
spend, run durable jobs, and retrieve receipts. This Antigravity plugin connects
over remote Streamable HTTP with **OAuth browser sign-in**.

## Install

Once listed in the Antigravity Plugin Marketplace:

1. Open **Customizations → Marketplace**
2. Install **Hydracept**
3. When Antigravity opens a browser, sign in to Hydracept and choose **Allow**

Until the Marketplace listing is live, install from this directory:

```bash
agy plugin install ./public/agents/antigravity
# or, after cloning zencodeinc/hydracept-public:
agy plugin install ./public/agents/antigravity
```

## Manual MCP config

```json
{
  "mcpServers": {
    "hydracept": {
      "serverUrl": "https://api.hydracept.com/mcp/antigravity"
    }
  }
}
```

Do **not** paste a Hydracept API key. This URL rejects API keys and uses OAuth
with dynamic client registration and PKCE S256.

## Scope

This connector includes text, reasoning, structured execution, classification,
translation, embeddings, domains, quotes, durable jobs, and receipts.

It does **not** generate images, video, audio, or 3D, and it does not transfer
money.

The full hosted catalog at `https://api.hydracept.com/mcp` is a separate API-key
surface and is not this marketplace plugin.

## Docs

- Product page: https://hydracept.com/antigravity/
- Privacy: https://hydracept.com/privacy.html
- Terms: https://hydracept.com/terms.html
- Support: support@hydracept.com

A Zencode product · © Zencode Consulting Inc.
