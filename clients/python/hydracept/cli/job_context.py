"""Merge ready-workspace identity into portable capability job payloads."""

from __future__ import annotations

from typing import Any

from hydracept.cli.workspace import ResolvedWorkspace


class WorkspaceContextError(ValueError):
    """Caller context disagrees with the bound checkout identity."""


def merge_workspace_job_context(
    payload: dict[str, Any],
    workspace: ResolvedWorkspace | None,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill workspace identity and drop stale execution.quoteId / estimateId.

    Precedence: explicit caller context > workspace-derived context > no context.
    A different explicit projectId than the bound workspace is rejected.
    Applying the same identity twice is a no-op.
    """
    del config  # identity never comes from config.json
    merged = dict(payload)
    context = dict(merged.get("context") or {})
    bound_project = str(workspace.project_id or "").strip() if workspace is not None else ""
    bound_environment = str(workspace.environment or "").strip() if workspace is not None else ""
    explicit_project = str(context.get("projectId") or "").strip()
    if explicit_project and bound_project and explicit_project != bound_project:
        raise WorkspaceContextError(
            f"context.projectId={explicit_project} disagrees with workspace "
            f"projectId={bound_project}"
        )
    if not explicit_project and bound_project:
        context["projectId"] = bound_project
    if not str(context.get("productId") or "").strip() and bound_project:
        context["productId"] = bound_project
    if not str(context.get("environment") or "").strip() and bound_environment:
        context["environment"] = bound_environment
    merged["context"] = context
    execution = merged.get("execution")
    if isinstance(execution, dict):
        cleaned = dict(execution)
        cleaned.pop("quoteId", None)
        cleaned.pop("estimateId", None)
        merged["execution"] = cleaned
    return merged
