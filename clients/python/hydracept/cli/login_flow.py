"""Device login and credential storage (ADR-019 / ADR-020)."""

from __future__ import annotations

import sys
import time
import webbrowser
from pathlib import Path

import httpx
from rich.console import Console

from hydracept.cli.bootstrap import ensure_gitignore, write_secrets
from hydracept.cli.exit_codes import USAGE
from hydracept.cli.session_store import DEFAULT_APP_BASE_URL, HumanSession, save_session


class LoginError(Exception):
    def __init__(self, message: str, exit_code: int = USAGE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def store_token(project_root: Path, token: str, *, kind: str = "api_key") -> None:
    payload = (
        {"apiKey": token, "kind": kind, "schemaVersion": 2}
        if kind == "api_key"
        else {"token": token, "kind": kind}
    )
    write_secrets(project_root, payload)
    ensure_gitignore(project_root)


def login_with_token(
    project_root: Path,
    token: str,
    *,
    console: Console | None = None,
) -> None:
    pasted = (token or "").strip()
    if pasted == "-":
        pasted = sys.stdin.read().strip()
    if not pasted:
        raise LoginError("Empty --token")
    store_token(project_root, pasted, kind="api_key")
    if console is not None:
        console.print("[green]Stored API key[/green] in .hydracept/secrets.json")
        console.print("Next: [bold]python -m hydracept configure[/bold]")
        console.print("Or: [bold]python -m hydracept keys create --configure[/bold] (after device login)")


def login_device(
    project_root: Path,
    api: str,
    *,
    app_url: str | None = None,
    open_browser: bool = True,
    console: Console | None = None,
) -> None:
    _ = project_root
    app_base = (app_url or DEFAULT_APP_BASE_URL).rstrip("/")
    start = httpx.post(f"{app_base}/v1/auth/device/start", timeout=30.0)
    start.raise_for_status()
    payload = start.json()
    user_code = payload.get("userCode") or payload.get("user_code")
    verification = (
        payload.get("verificationUri")
        or payload.get("verification_uri")
        or f"{app_base}/device"
    )
    if console is not None:
        console.print("[bold]Starting Hydracept authentication...[/bold]")
    if user_code and "user_code=" not in str(verification):
        sep = "&" if "?" in str(verification) else "?"
        verification = f"{verification}{sep}user_code={user_code}"
    if console is not None:
        console.print(f"Open: [cyan]{verification}[/cyan]")
        console.print(f"Code: [bold]{user_code}[/bold]")
    if open_browser:
        try:
            webbrowser.open(str(verification))
        except Exception:
            pass
    device_code = payload.get("deviceCode") or payload.get("device_code")
    while True:
        token_resp = httpx.post(
            f"{app_base}/v1/auth/device/token",
            json={"deviceCode": device_code},
            timeout=30.0,
        )
        if token_resp.status_code == 428:
            time.sleep(2)
            continue
        token_resp.raise_for_status()
        data = token_resp.json()
        session_token = data.get("sessionToken")
        csrf_token = data.get("csrfToken")
        principal_id = data.get("principalId")
        if not session_token or not csrf_token or not principal_id:
            raise LoginError("No session in device response")
        save_session(
            HumanSession(
                session_token=str(session_token),
                csrf_token=str(csrf_token),
                principal_id=str(principal_id),
                app_base_url=str(data.get("appBaseUrl") or app_base),
            )
        )
        if console is not None:
            console.print("[green]Signed in to Hydracept.[/green]")
            console.print("\nNext:\n  python -m hydracept keys create --configure")
        return
