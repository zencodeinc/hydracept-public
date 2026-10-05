"""Retry transient HTTP failures with exponential backoff."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

import httpx

from hydracept.errors import HydraceptApiError, raise_api_status

T = TypeVar("T")

_RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})


def is_retryable_status(status_code: int) -> bool:
    return status_code in _RETRYABLE


def request_with_retry(
    send: Callable[[], httpx.Response],
    *,
    max_attempts: int = 5,
    base_delay_seconds: float = 0.5,
    max_retry_after_seconds: float = 30.0,
) -> httpx.Response:
    last_response: httpx.Response | None = None
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = send()
        except (httpx.TransportError, TimeoutError) as exc:
            last_error = exc
            if attempt >= max_attempts:
                raise
            time.sleep(base_delay_seconds * (2 ** (attempt - 1)))
            continue
        if response.is_success or not is_retryable_status(response.status_code):
            return response
        last_response = response
        if attempt >= max_attempts:
            break
        delay = base_delay_seconds * (2 ** (attempt - 1))
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = min(max_retry_after_seconds, max(delay, float(retry_after)))
            except ValueError:
                pass
        time.sleep(delay)
    if last_response is not None:
        return last_response
    assert last_error is not None
    raise last_error


def post_json_with_retry(
    client: httpx.Client,
    path: str,
    body: dict | None,
    *,
    timeout: httpx.Timeout | None = None,
    max_attempts: int = 5,
) -> dict:
    def _send() -> httpx.Response:
        headers: dict[str, str] = {}
        if isinstance(body, dict):
            idem = body.get("idempotencyKey")
            if isinstance(idem, str) and idem.strip():
                headers["Idempotency-Key"] = idem.strip()
        return client.post(path, json=body, headers=headers, timeout=timeout)

    response = request_with_retry(_send, max_attempts=max_attempts)
    raise_api_status(response)
    if not response.content:
        return {}
    return response.json()
