# Hydracept for ChatGPT and Codex

Hydracept is an execution control plane for agents: discover capabilities, quote
spend, run durable jobs, and retrieve receipts. This plugin connects over remote
Streamable HTTP with **OAuth browser sign-in** (DCR + PKCE S256).

## Endpoint

`https://api.hydracept.com/mcp/openai`

Do **not** paste a Hydracept API key. This URL rejects API keys.

## ChatGPT

1. Add a custom MCP server (or install from the shared ChatGPT/Codex plugin
   directory once published).
2. Use MCP server URL `https://api.hydracept.com/mcp/openai`.
3. Choose OAuth and complete the browser sign-in.

## Codex CLI

```bash
codex mcp add hydracept --url https://api.hydracept.com/mcp/openai
codex mcp login hydracept
```

## Scope

This connector includes text, reasoning, structured execution, classification,
translation, embeddings, domains, quotes, durable jobs, and receipts.

It does **not** generate images, video, audio, or 3D, and it does not transfer
money.

The full hosted catalog at `https://api.hydracept.com/mcp` is a separate API-key
surface and is not this ChatGPT/Codex listing.

## Docs

- Product page: https://hydracept.com/openai/
- Privacy: https://hydracept.com/privacy.html
- Terms: https://hydracept.com/terms.html
- Support: support@hydracept.com

A Zencode product · © Zencode Consulting Inc.
