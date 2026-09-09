"""Non-secret runtime attestation for checkout-bound stdio MCP servers.

On-disk MCP configuration proves only what a host *may* launch.  It does not
prove which already-running server instance the host is currently using.  This
module records the identity of a live stdio process in its checkout so init and
doctor can distinguish configured state from active state.

The lease intentionally contains no API keys, bearer tokens, prompts, or other
customer data.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from hydracept.cli.workspace_fingerprint import workspace_fingerprint

_RUNTIME_FILENAME = "mcp-runtime.json"
_SERVER_INSTANCE_ID = f"mcp_{uuid.uuid4().hex[:20]}"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _project_id(root: Path) -> str | None:
    value = _read_json(root / ".hydracept" / "project.json").get("projectId")
    text = str(value or "").strip()
    return text or None


def runtime_binding_path(project_root: Path | str) -> Path:
    return Path(project_root).resolve() / ".hydracept" / _RUNTIME_FILENAME


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # On Windows a dead PID may surface as a generic OSError.  Treat an
        # unprovable process as stale; a false "live" answer is the unsafe one.
        return False
    return True


def attest_runtime_binding(
    project_root: Path | str,
    *,
    source: str,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Atomically publish this MCP process's checkout identity."""
    root = Path(project_root).resolve()
    environ = os.environ if env is None else env
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "serverInstanceId": _SERVER_INSTANCE_ID,
        "pid": os.getpid(),
        "startedAt": datetime.now(UTC).isoformat(),
        "bindingSource": source,
        "workspaceFingerprint": workspace_fingerprint(root),
        "executionProjectId": _project_id(root),
        "generation": str(environ.get("HYDRACEPT_MCP_GENERATION") or "").strip() or None,
    }
    path = runtime_binding_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return payload


@dataclass(frozen=True)
class RuntimeBindingStatus:
    verified: bool
    status: str
    server_instance_id: str | None = None
    generation: str | None = None
    workspace_fingerprint: str | None = None
    execution_project_id: str | None = None
    binding_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtimeVerified": self.verified,
            "runtimeStatus": self.status,
            "serverInstanceId": self.server_instance_id,
            "activeGeneration": self.generation,
            "activeWorkspaceFingerprint": self.workspace_fingerprint,
            "activeExecutionProjectId": self.execution_project_id,
            "bindingSource": self.binding_source,
        }


def inspect_runtime_binding(
    project_root: Path | str,
    *,
    expected_generations: Iterable[str] = (),
) -> RuntimeBindingStatus:
    """Verify the live lease against the checkout and current MCP config."""
    root = Path(project_root).resolve()
    payload = _read_json(runtime_binding_path(root))
    if not payload:
        return RuntimeBindingStatus(False, "missing")

    try:
        pid = int(payload.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if not _pid_alive(pid):
        return RuntimeBindingStatus(False, "stale")

    active_fingerprint = str(payload.get("workspaceFingerprint") or "") or None
    expected_fingerprint = workspace_fingerprint(root)
    active_project = str(payload.get("executionProjectId") or "") or None
    expected_project = _project_id(root)
    generation = str(payload.get("generation") or "") or None
    source = str(payload.get("bindingSource") or "") or None
    instance = str(payload.get("serverInstanceId") or "") or None

    if active_fingerprint != expected_fingerprint:
        return RuntimeBindingStatus(
            False, "workspace_mismatch", instance, generation, active_fingerprint, active_project, source
        )
    if expected_project and active_project != expected_project:
        return RuntimeBindingStatus(
            False, "project_mismatch", instance, generation, active_fingerprint, active_project, source
        )

    configured_generations = {str(value).strip() for value in expected_generations if str(value).strip()}
    if configured_generations and generation not in configured_generations:
        return RuntimeBindingStatus(
            False, "generation_mismatch", instance, generation, active_fingerprint, active_project, source
        )

    return RuntimeBindingStatus(
        True, "verified", instance, generation, active_fingerprint, active_project, source
    )
