"""CLI re-export of shared client identity headers."""

from hydracept.client_identity import (
    HYDRACEPT_CLIENT_HEADER,
    hydracept_client_headers,
    hydracept_client_version,
)

__all__ = [
    "HYDRACEPT_CLIENT_HEADER",
    "hydracept_client_headers",
    "hydracept_client_version",
]
