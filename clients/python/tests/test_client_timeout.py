"""HydraceptClient timeout and stdio setup."""

from __future__ import annotations

import httpx

from hydracept import HydraceptClient, _http_timeout


def test_http_timeout_uses_short_connect() -> None:
    timeout = _http_timeout(120.0)
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 10.0
    assert timeout.read == 120.0


def test_client_init_stores_timeout() -> None:
    with HydraceptClient("https://api.example.test", "tok_test") as client:
        assert isinstance(client._timeout, httpx.Timeout)
        assert client._timeout.connect == 10.0


def test_pinned_read_timeout_covers_admission_plus_execution() -> None:
    from hydracept.http_timeout import PINNED_READ_TIMEOUT_SECONDS

    timeout = _http_timeout(PINNED_READ_TIMEOUT_SECONDS)
    assert timeout.read == 2460.0
    assert timeout.connect == 10.0
