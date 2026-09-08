"""HTTP bridge from first-party local identity proofs to Hydracept sessions."""

from __future__ import annotations

from typing import Any

import httpx

from hydracept.cli.identity.adapters import LocalIdentityHint, LocalIdentityProof
from hydracept.cli.session_store import DEFAULT_APP_BASE_URL, HumanSession, save_session
from hydracept.cli.workspace import DEFAULT_API

IDENTITY_ASSERTION_SCHEMA = "hydracept.identity.assertion.v1"
IDENTITY_SESSION_SCHEMA = "hydracept.identity.session.v1"
_TRUSTED_APP_BASE_URL = DEFAULT_APP_BASE_URL.rstrip("/")
_TRUSTED_API_BASE_URL = DEFAULT_API.rstrip("/")

# Assertion credentials are intentionally process-local until the canonical
# bootstrap /complete authority succeeds. They must not create a durable
# Hydracept login that can make init bypass a failed bootstrap handoff.
_TRANSIENT_SESSIONS: dict[str, HumanSession] = {}


class LocalIdentityClientError(RuntimeError):
    """Sanitized local identity transport/protocol failure.

    Never retain an httpx Request/Response here: those objects may contain the
    foreign GitHub proof or the transient Hydracept session cookie.
    """


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, str) and detail:
                return detail
    except Exception:
        pass
    return f"HTTP {response.status_code}"


def _post(*args: Any, **kwargs: Any) -> httpx.Response:
    try:
        return httpx.post(*args, **kwargs)
    except httpx.HTTPError:
        # Do not chain transport errors. httpx exceptions retain Request objects,
        # which can contain secret-bearing request bodies/headers.
        raise LocalIdentityClientError("Hydracept identity request failed") from None


def assert_local_identity(
    *,
    hint: LocalIdentityHint,
    proof: LocalIdentityProof,
    bootstrap_session_id: str,
) -> dict[str, Any]:
    """Verify one proof and retain its Hydracept session only in this process.

    Foreign proofs are always submitted to the pinned first-party Hydracept app
    origin. HYDRACEPT_APP_URL is deliberately ignored here: a mutable local
    environment variable must never be able to redirect a GitHub credential.
    """
    if proof.provider != hint.provider:
        raise ValueError("Local identity proof/provider mismatch")
    response = _post(
        f"{_TRUSTED_APP_BASE_URL}/v1/auth/identity-assertions",
        json={
            "schemaVersion": IDENTITY_ASSERTION_SCHEMA,
            "provider": hint.provider,
            "bootstrapSessionId": bootstrap_session_id,
            "proof": proof.to_wire(),
        },
        timeout=30.0,
    )
    if response.is_error:
        message = _error_message(response)
        # Do not raise HTTPStatusError: it retains response.request, including the
        # serialized GitHub proof in this request body.
        del response
        raise LocalIdentityClientError(message)
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Identity assertion returned an invalid response")
    if str(body.get("schemaVersion") or "") != IDENTITY_SESSION_SCHEMA:
        raise ValueError("Identity assertion returned an unsupported session schema")
    identity = body.get("identity")
    if not isinstance(identity, dict) or str(identity.get("provider") or "") != hint.provider:
        raise ValueError("Identity assertion returned a different provider")

    session_token = str(body.get("sessionToken") or "").strip()
    csrf_token = str(body.get("csrfToken") or "").strip()
    principal_id = str(body.get("principalId") or "").strip()
    if not session_token or not csrf_token or not principal_id:
        raise ValueError("Identity assertion did not return a complete Hydracept session")

    _TRANSIENT_SESSIONS[bootstrap_session_id] = HumanSession(
        session_token=session_token,
        csrf_token=csrf_token,
        principal_id=principal_id,
        app_base_url=_TRUSTED_APP_BASE_URL,
    )
    return body


def complete_bootstrap_with_session(
    *,
    api_url: str,
    bootstrap_session_id: str,
    project_id: str,
    environment: str,
) -> dict[str, Any]:
    """Complete bootstrap with the transient session, then persist that session.

    Automatic foreign-credential exchange is production-origin only. In
    particular, a custom HYDRACEPT_API_URL or --api-url target may not receive a
    Hydracept human session minted from a local GitHub credential.
    """
    session = _TRANSIENT_SESSIONS.pop(bootstrap_session_id, None)
    if session is None:
        raise RuntimeError("Hydracept identity assertion session is unavailable")

    api = api_url.rstrip("/")
    if api != _TRUSTED_API_BASE_URL:
        raise RuntimeError(
            "automatic local identity is only supported against the official Hydracept API"
        )

    response = _post(
        f"{api}/v1/bootstrap/sessions/{bootstrap_session_id}/complete",
        headers={
            "Cookie": (
                f"hydracept_session={session.session_token}; "
                f"hydracept_csrf={session.csrf_token}"
            ),
            "X-CSRF-Token": session.csrf_token,
            "Content-Type": "application/json",
        },
        json={
            "projectId": project_id,
            "environment": environment,
            "approveMachine": True,
        },
        timeout=30.0,
    )
    if response.is_error:
        message = _error_message(response)
        # The failed request carries the transient Hydracept session cookie.
        del response
        raise LocalIdentityClientError(message)
    body = response.json()
    if not isinstance(body, dict) or str(body.get("status") or "") != "approved":
        raise ValueError("Bootstrap completion returned an invalid response")

    # Only canonical bootstrap completion makes this login durable. If assertion
    # or completion fails, init falls back without leaving a session that can
    # bypass the pending bootstrap state machine on the next run.
    save_session(session)
    return body
