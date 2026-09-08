"""HTTP client for app-origin session APIs."""

from __future__ import annotations

from typing import Any

import httpx

from hydracept.cli.session_store import HumanSession, SESSION_EXPIRED_MESSAGE, load_session


class SessionClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _session_headers(session: HumanSession) -> dict[str, str]:
    return {
        "Cookie": (
            f"hydracept_session={session.session_token}; "
            f"hydracept_csrf={session.csrf_token}"
        ),
        "X-CSRF-Token": session.csrf_token,
        "Content-Type": "application/json",
    }


def _session_cookie_headers(session: HumanSession) -> dict[str, str]:
    return {"Cookie": f"hydracept_session={session.session_token}"}


def _response_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        detail = body.get("detail")
        if isinstance(detail, list):
            return str(detail)
        if isinstance(detail, str) and detail.strip():
            return detail
        return str(body)
    except Exception:
        text = (response.text or "").strip()
        return text or f"HTTP {response.status_code}"


def _handle_response(response: httpx.Response) -> Any:
    if response.status_code == 401:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    if response.is_error:
        raise SessionClientError(
            _response_error_message(response),
            status_code=response.status_code,
        )
    if not response.content:
        return {}
    return response.json()


def fetch_session_context() -> dict[str, Any]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{session.app_base_url}/v1/session/context",
            headers=_session_cookie_headers(session),
        )
    payload = _handle_response(response)
    if not isinstance(payload, dict):
        return {}
    return payload


def organization_id_from_session_context(context: dict[str, Any] | None) -> str | None:
    payload = context if isinstance(context, dict) else {}
    organization = payload.get("organization")
    if not isinstance(organization, dict):
        return None
    org_id = str(organization.get("id") or "").strip()
    return org_id or None


def project_from_session_context(context: dict[str, Any]) -> str:
    if context.get("needsOnboarding"):
        return ""
    project = context.get("project")
    if isinstance(project, dict) and project.get("id"):
        return str(project["id"])
    if context.get("productId"):
        return str(context["productId"])
    return ""


def environment_from_session_context(
    context: dict[str, Any],
    *,
    default: str = "development",
) -> str:
    environment = context.get("environment")
    if isinstance(environment, dict) and environment.get("slug"):
        return str(environment["slug"])
    if isinstance(environment, str) and environment.strip():
        return environment.strip()
    return default


def list_keys(*, include_revoked: bool = False) -> dict[str, Any]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    params = {"includeRevoked": "true"} if include_revoked else {}
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{session.app_base_url}/v1/api-keys",
            headers=_session_cookie_headers(session),
            params=params,
        )
    return _handle_response(response)


def create_key(
    *,
    name: str,
    project_id: str,
    environment: str,
) -> dict[str, Any]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{session.app_base_url}/v1/api-keys",
            headers=_session_headers(session),
            json={
                "name": name,
                "projectId": project_id,
                "environment": environment,
            },
        )
    return _handle_response(response)


def revoke_key(key_id: str) -> dict[str, Any]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    with httpx.Client(timeout=30.0) as client:
        response = client.delete(
            f"{session.app_base_url}/v1/api-keys/{key_id}",
            headers=_session_headers(session),
        )
    return _handle_response(response)


def identity_from_session_context(context: dict[str, Any] | None) -> dict[str, Any]:
    payload = context if isinstance(context, dict) else {}
    identity = payload.get("identity")
    if isinstance(identity, dict) and identity:
        provider = str(identity.get("provider") or "").strip() or None
        account = str(identity.get("account") or identity.get("displayName") or "").strip() or None
        authenticated = bool(identity.get("authenticated", True))
        return {
            "provider": provider,
            "account": account,
            "authenticated": authenticated,
        }
    return {"provider": None, "account": None, "authenticated": False}


def list_organizations() -> list[dict[str, Any]]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{session.app_base_url}/v1/organizations",
            headers=_session_cookie_headers(session),
        )
    payload = _handle_response(response)
    items = payload.get("items") if isinstance(payload, dict) else payload
    return [item for item in items or [] if isinstance(item, dict)]


def list_organization_projects(organization_id: str) -> list[dict[str, Any]]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{session.app_base_url}/v1/organizations/{organization_id}/projects",
            headers=_session_cookie_headers(session),
        )
    payload = _handle_response(response)
    items = payload.get("items") if isinstance(payload, dict) else payload
    return [item for item in items or [] if isinstance(item, dict)]


def create_organization_project(
    organization_id: str,
    *,
    display_name: str,
    environment: str = "development",
    repository: dict[str, str] | None = None,
) -> dict[str, Any]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    body: dict[str, Any] = {
        "displayName": display_name,
        "environment": environment,
    }
    if repository:
        body["repository"] = repository
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{session.app_base_url}/v1/organizations/{organization_id}/projects",
            headers=_session_headers(session),
            json=body,
        )
    payload = _handle_response(response)
    return payload if isinstance(payload, dict) else {}


def bootstrap_onboarding_project(
    *,
    display_name: str,
    repository: dict[str, str] | None = None,
    environment: str = "development",
) -> dict[str, Any]:
    session = load_session()
    if session is None:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    body: dict[str, Any] = {"projectName": display_name}
    if repository:
        body["repository"] = repository
    env = (environment or "").strip()
    if env and env != "development":
        body["environment"] = env
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{session.app_base_url}/v1/onboarding/bootstrap",
            headers=_session_headers(session),
            json=body,
        )
    payload = _handle_response(response)
    return payload if isinstance(payload, dict) else {}
