"""Provider-neutral local workspace/repository context for project resolution."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ContextField:
    value: str | None
    confidence: Confidence
    provenance: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class LocalProjectContext:
    workspace_root: ContextField
    display_name: ContextField
    git_root: ContextField
    git_remote: ContextField
    repository_provider: ContextField
    repository_owner: ContextField
    repository_name: ContextField
    ide: ContextField

    @property
    def root(self) -> Path:
        return Path(self.workspace_root.value or ".").resolve()

    @property
    def inferred_name(self) -> str:
        return str(self.display_name.value or self.root.name or "project").strip()

    @property
    def has_github_repository(self) -> bool:
        return bool(
            self.repository_provider.value == "github"
            and self.repository_owner.value
            and self.repository_name.value
        )

    def repository_payload(self) -> dict[str, str] | None:
        if not self.has_github_repository:
            return None
        payload = {
            "provider": "github",
            "owner": str(self.repository_owner.value),
            "name": str(self.repository_name.value),
        }
        remote = str(self.git_remote.value or "").strip()
        if remote:
            payload["url"] = remote
        return payload

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspaceRoot": self.workspace_root.as_dict(),
            "displayName": self.display_name.as_dict(),
            "gitRoot": self.git_root.as_dict(),
            "gitRemote": self.git_remote.as_dict(),
            "repositoryProvider": self.repository_provider.as_dict(),
            "repositoryOwner": self.repository_owner.as_dict(),
            "repositoryName": self.repository_name.as_dict(),
            "ide": self.ide.as_dict(),
        }


_GITHUB_REMOTE = re.compile(
    r"(?:github\.com[:/]|github\.com:)(?P<owner>[^/]+)/(?P<name>[^/\s]+)$",
    re.IGNORECASE,
)


def _empty(provenance: str, confidence: Confidence = "low") -> ContextField:
    return ContextField(value=None, confidence=confidence, provenance=provenance)


def _run_git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def parse_github_remote(url: str) -> tuple[str, str] | None:
    raw = (url or "").strip()
    if not raw:
        return None
    cleaned = raw.replace("\\", "/")
    cleaned = cleaned.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    cleaned = re.sub(r"\.git$", "", cleaned, flags=re.IGNORECASE).rstrip("/")
    match = _GITHUB_REMOTE.search(cleaned)
    if match is None:
        return None
    owner = match.group("owner").strip()
    name = match.group("name").strip().rstrip("/")
    if not owner or not name:
        return None
    return owner, name


def detect_ide() -> ContextField:
    if os.environ.get("CURSOR_AGENT", "").strip() or os.environ.get(
        "CURSOR_EXTENSION_HOST_ROLE", ""
    ).strip():
        return ContextField("cursor", "high", "env:CURSOR_AGENT")
    if os.environ.get("CLAUDE_PROJECT_DIR", "").strip():
        return ContextField("claude", "high", "env:CLAUDE_PROJECT_DIR")
    term = (os.environ.get("TERM_PROGRAM") or "").strip().lower()
    if term == "vscode":
        return ContextField("vscode", "medium", "env:TERM_PROGRAM")
    if os.environ.get("VSCODE_PID", "").strip():
        return ContextField("vscode", "medium", "env:VSCODE_PID")
    return _empty("none")


def github_cli_login() -> str | None:
    try:
        completed = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    login = (completed.stdout or "").strip()
    return login or None


def resolve_local_project_context(project_root: Path) -> LocalProjectContext:
    root = project_root.resolve()
    workspace_root = ContextField(str(root), "high", "cli:cwd")
    ide = detect_ide()

    git_root_raw = _run_git(root, "rev-parse", "--show-toplevel")
    git_root = (
        ContextField(git_root_raw, "high", "git:rev-parse")
        if git_root_raw
        else _empty("git:unavailable")
    )
    git_cwd = Path(git_root_raw) if git_root_raw else root
    git_remote_raw = _run_git(git_cwd, "remote", "get-url", "origin")
    if not git_remote_raw:
        git_remote_raw = _run_git(git_cwd, "config", "--get", "remote.origin.url")
    git_remote = (
        ContextField(git_remote_raw, "high", "git:remote.origin")
        if git_remote_raw
        else _empty("git:no-origin")
    )

    parsed = parse_github_remote(git_remote_raw or "")
    if parsed is not None:
        owner, name = parsed
        repository_provider = ContextField("github", "high", "git:remote.origin")
        repository_owner = ContextField(owner, "high", "git:remote.origin")
        repository_name = ContextField(name, "high", "git:remote.origin")
        display_name = ContextField(name, "high", "git:repository-name")
    elif git_root_raw:
        folder = Path(git_root_raw).name
        repository_provider = _empty("git:non-github-remote")
        repository_owner = _empty("git:non-github-remote")
        repository_name = _empty("git:non-github-remote")
        display_name = ContextField(folder, "medium", "git:root-basename")
    else:
        repository_provider = _empty("git:unavailable")
        repository_owner = _empty("git:unavailable")
        repository_name = _empty("git:unavailable")
        display_name = ContextField(root.name, "medium", "workspace:basename")

    return LocalProjectContext(
        workspace_root=workspace_root,
        display_name=display_name,
        git_root=git_root,
        git_remote=git_remote,
        repository_provider=repository_provider,
        repository_owner=repository_owner,
        repository_name=repository_name,
        ide=ide,
    )
