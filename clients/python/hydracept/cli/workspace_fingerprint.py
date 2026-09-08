"""Opaque workspace fingerprint for Connect trust (0.3.11 consumer-trust)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from hydracept.cli.machine import machine_fingerprint


def _stable_checkout_identity(project_root: Path, binding: dict[str, Any]) -> str:
    project_id = str(binding.get("projectId") or "").strip()
    if project_id:
        return f"project:{project_id}"

    repository = binding.get("repository")
    if isinstance(repository, dict):
        provider = str(repository.get("provider") or "").strip().lower()
        owner = str(repository.get("owner") or "").strip().lower()
        name = str(repository.get("name") or "").strip().lower()
        if provider and owner and name:
            return f"repo:{provider}/{owner}/{name}"

    from hydracept.cli.local_project_context import resolve_local_project_context

    context = resolve_local_project_context(project_root)
    if context.has_github_repository:
        return (
            "repo:github/"
            f"{str(context.repository_owner.value or '').strip().lower()}/"
            f"{str(context.repository_name.value or '').strip().lower()}"
        )

    folder_name = str(context.inferred_name or project_root.resolve().name or "project").strip().lower()
    return f"folder:{folder_name}"


def workspace_fingerprint(project_root: Path, binding: dict[str, Any] | None = None) -> str:
    """Return a stable opaque fingerprint for the checkout, not a raw path."""
    from hydracept.cli.project import load_project_binding

    resolved_binding = dict(binding or load_project_binding(project_root) or {})
    identity = _stable_checkout_identity(Path(project_root), resolved_binding)
    material = f"{machine_fingerprint()}\0{identity}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"wsf_{digest}"
