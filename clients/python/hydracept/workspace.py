"""HydraceptWorkspace — checkout identity from project.json, then Client + JobRunner."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

from hydracept.cli.workspace import (
    WorkspaceIdentityError,
    WorkspaceNotReadyError,
    require_ready_workspace,
)
from hydracept.jobs import JobRunner

if TYPE_CHECKING:
    from hydracept import HydraceptClient


class HydraceptWorkspace:
    """Absolute checkout identity. ``open()`` never takes a project-id override."""

    def __init__(self, client: HydraceptClient, jobs: JobRunner, root: Path) -> None:
        self.client = client
        self.jobs = jobs
        self.root = root

    @classmethod
    def open(cls, root: str | Path | None = None) -> HydraceptWorkspace:
        from hydracept import HydraceptClient

        project_root = Path(root).resolve() if root else Path.cwd().resolve()
        try:
            resolved = require_ready_workspace(project_root)
        except WorkspaceIdentityError as extra:
            raise WorkspaceNotReadyError(str(extra)) from extra
        client = HydraceptClient(resolved.api_url, resolved.token, workspace=resolved)
        jobs = JobRunner(client, resolved)
        return cls(client, jobs, project_root)

    def invoke(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        """Convenience façade over the bound client — not a second merge implementation."""
        return self.client.invoke_capability(key, body)

    def __enter__(self) -> HydraceptWorkspace:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None
