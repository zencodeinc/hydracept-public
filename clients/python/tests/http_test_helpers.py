"""Shared fakes for hermetic CLI HTTP tests."""

from __future__ import annotations

from typing import Any, Callable


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


def pending_bootstrap_session_get(
    session_id: str,
    *,
    connect_url: str | None = None,
    expires_at: str = "2030-01-01T00:00:00+00:00",
    activation_url: str | None = None,
) -> Callable[..., FakeResponse]:
    url = connect_url or f"https://app.hydracept.com/connect/{session_id}?token=opaque-token"

    def fake_get(request_url: str, **kwargs: object) -> FakeResponse:
        if f"/v1/bootstrap/sessions/{session_id}" not in request_url:
            raise AssertionError(f"unexpected get {request_url!r}")
        payload: dict[str, Any] = {
            "sessionId": session_id,
            "status": "pending",
            "connectUrl": url,
            "expiresAt": expires_at,
        }
        if activation_url is not None:
            payload["activationUrl"] = activation_url
        return FakeResponse(payload)

    return fake_get
