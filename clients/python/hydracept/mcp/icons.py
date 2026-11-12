"""Public brand icon advertised on the Hydracept MCP handshake."""

from __future__ import annotations

from mcp.types import Icon

# Full geometric H — hydracept.com/hydracept-logo.png and plugin assets/trademark.png.
# Cache-bust when the master mark bytes change (deploy serves the same path).
HYDRACEPT_LOGO_URL = "https://hydracept.com/hydracept-logo.png?v=20261112"


def hydracept_mcp_icons() -> list[Icon]:
    return [
        Icon(
            src=HYDRACEPT_LOGO_URL,
            mime_type="image/png",
            sizes=["any"],
        )
    ]
