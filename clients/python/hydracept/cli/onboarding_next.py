"""Canonical CLI onboarding next-step copy (ADR-020)."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.workspace import WorkspaceState, resolve_workspace, workspace_state

START_URL = "https://hydracept.com/start"


def credential_setup_next_steps(project_root: Path) -> list[str]:
    """Ordered setup commands for an unready workspace."""
    resolved = resolve_workspace(project_root)
    state = workspace_state(resolved)
    if state == WorkspaceState.READY:
        return []

    steps: list[str] = ["python -m hydracept init"]
    if resolved is None:
        steps.append(
            "With an existing API key: python -m hydracept init --token <HYDRACEPT_API_KEY> --apply --yes --json"
        )
    return steps


def no_credential_detail(project_root: Path) -> str:
    return (
        "No workspace API credential — run python -m hydracept init "
        f"(or see {START_URL})"
    )
