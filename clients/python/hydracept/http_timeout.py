"""HTTP timeout policy for the public Hydracept client."""

from __future__ import annotations

import httpx

CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 120.0
# Pinned POST waits on admission retries plus one provider execution.
# Platform max: 1800s admission + 600s execution + 60s slack.
PINNED_READ_TIMEOUT_SECONDS = 2460.0
PINNED_BULK_WAIT_TIMEOUT_SECONDS = 3600.0


def http_timeout(timeout: float = READ_TIMEOUT_SECONDS) -> httpx.Timeout:
    """Long read timeout for job submit; short connect so hung TLS fails fast."""
    connect = min(CONNECT_TIMEOUT_SECONDS, float(timeout)) if timeout else CONNECT_TIMEOUT_SECONDS
    return httpx.Timeout(timeout, connect=connect, pool=connect)
