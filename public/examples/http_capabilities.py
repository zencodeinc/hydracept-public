"""HTTP consumer example — list capabilities (public API)."""

import os
import urllib.request

API_URL = os.environ.get("HYDRACEPT_API_URL", "https://api.hydracept.com").rstrip("/")
API_KEY = os.environ.get("HYDRACEPT_API_KEY", "")

EXAMPLE = {
    "description": "List public capabilities with bearer auth",
    "request": {
        "method": "GET",
        "url": f"{API_URL}/v1/capabilities",
        "headers": {"Authorization": "Bearer <HYDRACEPT_API_KEY>"},
    },
}


def main() -> int:
    if not API_KEY:
        print("Set HYDRACEPT_API_KEY to run live example")
        return 0
    req = urllib.request.Request(
        f"{API_URL}/v1/capabilities",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    print(body[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
