"""Install `project up` as a login-persistent OS service.

The Hydracept API does not run the customer repo. This process must stay
alive on the machine that has the game checkout, independent of Cursor.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import hydracept
from hydracept.cli.bootstrap import ensure_gitignore
from hydracept.cli.login_flow import store_token
from hydracept.cli.secure_store import write_json_atomic
from hydracept.cli.workspace import config_path, read_json


class ProjectServiceError(Exception):
    """OS service install/uninstall failure."""


@dataclass(frozen=True)
class ProjectUpServiceSpec:
    project_root: Path
    api: str
    project_id: str | None = None
    python_executable: str = sys.executable


@dataclass(frozen=True)
class ProjectUpServiceStatus:
    name: str
    installed: bool
    running: bool
    detail: str = ""


class ProjectUpService(Protocol):
    def install(self, spec: ProjectUpServiceSpec) -> ProjectUpServiceStatus: ...

    def uninstall(self, project_root: Path) -> None: ...

    def status(self, project_root: Path) -> ProjectUpServiceStatus: ...

    def start(self, project_root: Path) -> None: ...


def service_id(project_root: Path) -> str:
    digest = hashlib.sha256(str(project_root.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"HydraceptProjectUp-{digest}"


def hydracept_pythonpath() -> str:
    return str(Path(hydracept.__file__).resolve().parent.parent)


def wrapper_path(project_root: Path) -> Path:
    suffix = ".cmd" if sys.platform == "win32" else ".sh"
    return Path(project_root).resolve() / ".hydracept" / f"project-up{suffix}"


def install_project_up(
    *,
    api: str,
    project_root: Path,
    token: str | None,
    project: str | None,
) -> ProjectUpServiceStatus:
    """Persist workspace credentials and register the login-persistent watcher."""
    persist_project_up_workspace(
        project_root,
        api=api,
        project_id=project,
        token=token,
    )
    spec = ProjectUpServiceSpec(
        project_root=Path(project_root).resolve(),
        api=api,
        project_id=project,
    )
    return detect_project_up_service().install(spec)


def persist_project_up_workspace(
    project_root: Path,
    *,
    api: str,
    project_id: str | None,
    token: str | None,
) -> None:
    root = Path(project_root).resolve()
    cfg_path = config_path(root)
    config = read_json(cfg_path)
    if project_id:
        from hydracept.cli.project import persist_config_without_identity, write_project_binding

        write_project_binding(
            root,
            {
                "projectId": project_id,
                "apiOrigin": api.rstrip("/"),
            },
        )
        persist_config_without_identity(root)
    else:
        write_json_atomic(cfg_path, config)
    if token and token.strip():
        store_token(root, token.strip(), kind="api_key")
    ensure_gitignore(root)
    gitignore = root / ".gitignore"
    extra = [
        ".hydracept/project-up.cmd",
        ".hydracept/project-up.sh",
        ".hydracept/project-up.xml",
        ".hydracept/project-up-launch.vbs",
        ".hydracept/project-up.lock",
        ".hydracept/project-up.pid",
    ]
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    additions = [line for line in extra if line not in existing]
    if additions:
        with gitignore.open("a", encoding="utf-8") as handle:
            handle.write("\n")
            for line in additions:
                handle.write(f"{line}\n")


def write_wrapper_script(spec: ProjectUpServiceSpec) -> Path:
    root = spec.project_root.resolve()
    path = wrapper_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    python = spec.python_executable
    pythonpath = hydracept_pythonpath()
    args = [
        python,
        "-m",
        "hydracept",
        "project",
        "up",
        "--project-root",
        str(root),
        "--api",
        spec.api.rstrip("/"),
    ]
    if spec.project_id:
        args.extend(["--project", spec.project_id])
    if sys.platform == "win32":
        quoted = " ".join(_cmd_quote(part) for part in args)
        body = (
            "@echo off\r\n"
            "set PYTHONIOENCODING=utf-8\r\n"
            f"set PYTHONPATH={pythonpath}\r\n"
            f"cd /d {_cmd_quote(str(root))}\r\n"
            ":loop\r\n"
            f"{quoted}\r\n"
            "timeout /t 60 /nobreak >nul\r\n"
            "goto loop\r\n"
        )
        path.write_text(body, encoding="utf-8")
    else:
        quoted = " ".join(_sh_quote(part) for part in args)
        body = (
            "#!/bin/sh\n"
            "set -eu\n"
            "export PYTHONIOENCODING=utf-8\n"
            f"export PYTHONPATH={_sh_quote(pythonpath)}\n"
            f"cd {_sh_quote(str(root))}\n"
            f"exec {quoted}\n"
        )
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    return path


def detect_project_up_service() -> ProjectUpService:
    if sys.platform == "win32":
        from hydracept.cli.project_service_windows import WindowsProjectUpService

        return WindowsProjectUpService()
    from hydracept.cli.project_service_posix import PosixProjectUpService

    return PosixProjectUpService()


def _cmd_quote(value: str) -> str:
    if not value or any(ch in value for ch in ' \t"&<>|^'):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
