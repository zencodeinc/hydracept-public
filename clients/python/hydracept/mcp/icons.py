"""Public brand icon advertised on the Hydracept MCP handshake."""

from __future__ import annotations

from mcp.types import Icon

# Stylized H — same asset as hydracept.com/hydracept-logo.png and plugin assets/logo.png.
HYDRACEPT_LOGO_URL = "https://hydracept.com/hydracept-logo.png"


def hydracept_mcp_icons() -> list[Icon]:
    return [
        Icon(
            src=HYDRACEPT_LOGO_URL,
            mime_type="image/png",
            sizes=["any"],
        )
    ]
