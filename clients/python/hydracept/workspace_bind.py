"""Fill portable job JSON with workspace project context when missing."""

from __future__ import annotations

from typing import Any, Protocol


class WorkspaceIdentity(Protocol):
    project_id: str
    environment: str


def inject_workspace_job_context(body: dict[str, Any], workspace: WorkspaceIdentity) -> dict[str, Any]:
    """Return a copy of *body* with context.projectId / productId / environment set if absent.

    Job JSON in a repo can stay portable. Agents should not have to paste project ids.
    Existing context keys are never overwritten.
    """
    payload = dict(body)
    context = dict(payload.get("context") or {})
    if workspace.project_id:
        context.setdefault("projectId", workspace.project_id)
        context.setdefault("productId", workspace.project_id)
    if workspace.environment:
        context.setdefault("environment", workspace.environment)
    payload["context"] = context
    return payload
