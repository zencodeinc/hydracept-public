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
        from hydracept.context import require_execution_context

        require_execution_context(self.root)
        return self.client.invoke_capability(key, body)

    def run(
        self,
        key: str,
        body: dict[str, Any],
        *,
        wait: bool = True,
        timeout: float | None = None,
        max_cost: float | None = None,
        idempotency_key: str | None = None,
        out: str | Path | None = None,
    ) -> dict[str, Any]:
        """hydracept.run-result.v1 façade. Semantic match of CLI `run` / MCP hydracept_run."""
        from hydracept.cli.run_facade import execute_run
        from hydracept.errors import RunAdmissionError

        outcome = execute_run(
            self.root,
            key,
            body,
            wait=wait,
            timeout=timeout,
            max_cost=max_cost,
            idempotency_key=idempotency_key,
            out=Path(out) if out else None,
        )
        if outcome.error is not None and outcome.result is None:
            raise RunAdmissionError(outcome.error.to_dict())
        payload = outcome.payload()
        if outcome.exit_code and outcome.result is None:
            raise RunAdmissionError(payload)
        return payload

    def __enter__(self) -> HydraceptWorkspace:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None
