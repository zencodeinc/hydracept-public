"""Workspace bootstrap and configure (ADR-019)."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from hydracept.cli.exit_codes import AUTH, CONNECTIVITY
from hydracept.cli.workspace import (
    CliOverrides,
    ResolvedWorkspace,
    WorkspaceState,
    auth_headers,
    config_dir,
    config_path,
    local_env_path,
    read_json,
    resolve_workspace,
    secrets_path,
    workspace_state,
)


@dataclass
class ConfigureResult:
    workspace: ResolvedWorkspace
    config_path: Path
    bootstrap_called: bool
    api_key_written: bool


class ConfigureError(Exception):
    def __init__(self, message: str, exit_code: int = CONNECTIVITY) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def detect_stack(project_root: Path) -> str:
    is_unity = (project_root / "Assets").exists() and (project_root / "ProjectSettings").exists()
    if is_unity:
        return "unity"
    if any(project_root.glob("*.csproj")) or (project_root / "Assets").exists():
        return "dotnet"
    if (project_root / "package.json").exists():
        return "node"
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return "python"
    return "unknown"


def _apply_session_context(config: dict[str, Any], ctx: dict[str, Any], project_root: Path) -> None:
    environment = ctx.get("environment")
    env_slug = ""
    if isinstance(environment, dict) and environment.get("slug"):
        env_slug = str(environment["slug"])
    elif isinstance(environment, str):
        env_slug = environment
    project = ctx.get("project")
    project_id = ""
    project_name = ""
    if isinstance(project, dict):
        project_id = str(project.get("id") or "")
        project_name = str(project.get("displayName") or "")
    org = ctx.get("organization")
    if isinstance(org, dict):
        if org.get("id"):
            config["organizationId"] = org["id"]
        if org.get("displayName"):
            config["organizationName"] = org["displayName"]
    if project_id:
        from hydracept.cli.project import load_project_binding, write_project_binding

        existing = load_project_binding(project_root)
        bound = str((existing or {}).get("projectId") or "").strip()
        if bound and bound != project_id:
            return
        write_project_binding(
            project_root,
            {
                "projectId": project_id,
                "environment": env_slug or "development",
                "apiOrigin": str(config.get("apiBaseUrl") or "https://api.hydracept.com"),
                "projectName": project_name,
            },
        )


def _session_has_usable_project(ctx: dict[str, Any]) -> bool:
    if ctx.get("needsOnboarding"):
        return False
    project = ctx.get("project")
    if isinstance(project, dict) and project.get("id"):
        return True
    return bool(ctx.get("productId"))


def write_secrets(project_root: Path, payload: dict[str, Any]) -> Path:
    from hydracept.cli.secure_store import write_json_atomic

    path = secrets_path(project_root)
    existing = read_json(path)
    merged = {**existing, **payload}
    if "schemaVersion" not in merged:
        merged["schemaVersion"] = 2
    write_json_atomic(path, merged)
    return path


def ensure_gitignore(project_root: Path) -> list[str]:
    gitignore = project_root / ".gitignore"
    hints = [
        ".hydracept/secrets.json",
        ".hydracept/bootstrap-session.json",
        ".hydracept/*.env",
        ".env.hydracept",
    ]
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    additions = [h for h in hints if h not in existing]
    if not additions:
        return []
    with gitignore.open("a", encoding="utf-8") as handle:
        handle.write("\n# Hydracept local secrets\n")
        for hint in additions:
            handle.write(f"{hint}\n")
    return additions


def write_local_env(project_root: Path, workspace: ResolvedWorkspace, api_key: str) -> Path:
    path = local_env_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"HYDRACEPT_API_URL={workspace.api_url}\n"
        f"HYDRACEPT_API_KEY={api_key}\n"
        f"HYDRACEPT_PROJECT={workspace.project_id}\n"
        f"HYDRACEPT_ENVIRONMENT={workspace.environment}\n",
        encoding="utf-8",
    )
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def run_configure(
    project_root: Path,
    *,
    api_url: str | None = None,
    token: str | None = None,
    rotate: bool = False,
) -> ConfigureResult:
    """Reconcile workspace until ready. Fast path skips bootstrap-free when session suffices."""
    cfg_dir = config_dir(project_root)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_path(project_root)

    base = resolve_workspace(
        project_root,
        overrides=CliOverrides(token=token, api_url=api_url),
    )
    if base is None:
        raise ConfigureError(
            "No workspace API credential — run python -m hydracept init --apply --yes --json",
            exit_code=AUTH,
        )

    secrets = read_json(secrets_path(project_root))
    human_token = base.token
    config: dict[str, Any] = {"detectedStack": detect_stack(project_root)}
    if cfg_path.exists():
        config = {**read_json(cfg_path), **config}

    bootstrap_called = False
    api_key_written = False
    existing_key = str(secrets.get("apiKey") or "")

    try:
        context_resp = httpx.get(
            f"{base.api_url}/v1/session/context",
            headers=auth_headers(human_token),
            timeout=30.0,
        )
        if context_resp.status_code == 200:
            ctx = context_resp.json()
            _apply_session_context(config, ctx, project_root)
            if _session_has_usable_project(ctx) and existing_key and not rotate:
                from hydracept.cli.project import persist_config_without_identity, strip_identity_from_config

                cfg_path.write_text(
                    json.dumps(strip_identity_from_config(config), indent=2) + "\n",
                    encoding="utf-8",
                )
                persist_config_without_identity(project_root)
                workspace = resolve_workspace(
                    project_root,
                    overrides=CliOverrides(
                        token=token,
                        api_url=api_url,
                        session_context=ctx,
                    ),
                )
                assert workspace is not None
                write_local_env(project_root, workspace, existing_key)
                return ConfigureResult(
                    workspace=workspace,
                    config_path=cfg_path,
                    bootstrap_called=False,
                    api_key_written=False,
                )
    except httpx.HTTPError as exc:
        raise ConfigureError(f"session/context failed: {exc}") from exc

    api_key: str | None = existing_key or None
    if not api_key or rotate:
        bootstrap_called = True
        try:
            bootstrap = httpx.post(
                f"{base.api_url}/v1/onboarding/bootstrap-free",
                headers=auth_headers(human_token),
                json={},
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise ConfigureError(f"bootstrap-free failed: {exc}") from exc

        if bootstrap.status_code < 400:
            body = bootstrap.json()
            api_key = body.get("apiKey") or body.get("token") or (body.get("credential") or {}).get("secret")
            if body.get("organizationId"):
                config["organizationId"] = body["organizationId"]
            from hydracept.cli.project import write_project_binding

            write_project_binding(
                project_root,
                {
                    "projectId": body.get("projectId") or "",
                    "environment": body.get("environment") or "development",
                    "apiOrigin": base.api_url,
                },
            )
        elif not api_key:
            raise ConfigureError(
                f"bootstrap-free failed ({bootstrap.status_code}). "
                "Run python -m hydracept init --apply --yes --json and follow its interaction_required action.url exactly.",
                exit_code=CONNECTIVITY,
            )

    from hydracept.cli.project import persist_config_without_identity, strip_identity_from_config

    cfg_path.write_text(
        json.dumps(strip_identity_from_config(config), indent=2) + "\n",
        encoding="utf-8",
    )
    persist_config_without_identity(project_root)

    if api_key:
        write_secrets(project_root, {"apiKey": api_key, "kind": "service_principal"})
        ensure_gitignore(project_root)
        api_key_written = True

    session_ctx: dict[str, Any] = {}
    try:
        context_resp = httpx.get(
            f"{base.api_url}/v1/session/context",
            headers=auth_headers(human_token),
            timeout=30.0,
        )
        if context_resp.status_code == 200:
            session_ctx = context_resp.json()
    except httpx.HTTPError:
        session_ctx = {}

    workspace = resolve_workspace(
        project_root,
        overrides=CliOverrides(token=api_key or token, api_url=api_url, session_context=session_ctx),
    )
    if workspace is None:
        raise ConfigureError("configure failed to resolve workspace", exit_code=AUTH)

    if api_key:
        write_local_env(project_root, workspace, api_key)

    if workspace_state(workspace) != WorkspaceState.READY:
        raise ConfigureError(
            "Workspace not ready after configure — run python -m hydracept init --apply --yes --json and follow its interaction contract.",
            exit_code=CONNECTIVITY,
        )

    return ConfigureResult(
        workspace=workspace,
        config_path=cfg_path,
        bootstrap_called=bootstrap_called,
        api_key_written=api_key_written,
    )
