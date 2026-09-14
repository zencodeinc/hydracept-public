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
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


def _windows_process_create_time(pid: int) -> datetime | None:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        ctime = wintypes.FILETIME()
        etime = wintypes.FILETIME()
        ktime = wintypes.FILETIME()
        utime = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(ctime),
            ctypes.byref(etime),
            ctypes.byref(ktime),
            ctypes.byref(utime),
        ):
            return None
        stamp = (ctime.dwHighDateTime << 32) | ctime.dwLowDateTime
        return datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=stamp / 10)
    finally:
        kernel32.CloseHandle(handle)


def _posix_process_create_time(pid: int) -> datetime | None:
    stat_path = Path(f"/proc/{pid}")
    try:
        return datetime.fromtimestamp(stat_path.stat().st_ctime, tz=UTC)
    except OSError:
        return None


def _process_create_time(pid: int) -> datetime | None:
    if pid == os.getpid():
        return None
    if sys.platform == "win32":
        return _windows_process_create_time(pid)
    return _posix_process_create_time(pid)


def _parse_started_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _pid_matches_lease(pid: int, started_at: datetime | None) -> bool:
    if not _pid_alive(pid):
        return False
    if pid == os.getpid():
        return True
    created = _process_create_time(pid)
    if created is None or started_at is None:
        # Could not prove the PID still belongs to the lease writer.
        return sys.platform != "win32"
    return created <= started_at + timedelta(seconds=5)


def attest_runtime_binding(
    project_root: Path | str,
    *,
    source: str,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Atomically publish this MCP process's checkout identity."""
    root = Path(project_root).resolve()
    environ = os.environ if env is None else env
    from hydracept import __version__ as hydracept_version

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "serverInstanceId": _SERVER_INSTANCE_ID,
        "pid": os.getpid(),
        "startedAt": datetime.now(UTC).isoformat(),
        "bindingSource": source,
        "workspaceRoot": str(root),
        "workspaceFingerprint": workspace_fingerprint(root),
        "executionProjectId": _project_id(root),
        "generation": str(environ.get("HYDRACEPT_MCP_GENERATION") or "").strip() or None,
        "version": str(hydracept_version),
        "mcpVersion": str(hydracept_version),
    }
    path = runtime_binding_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2) + "\n"
    existing = _read_json(path)
    if _lease_equivalent(existing, payload):
        return payload
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(encoded, encoding="utf-8")
    try:
        _atomic_replace(temporary, path)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        if _lease_equivalent(_read_json(path), payload):
            return payload
        raise
    return payload


def _lease_equivalent(existing: dict[str, Any], payload: dict[str, Any]) -> bool:
    keys = (
        "serverInstanceId",
        "pid",
        "workspaceRoot",
        "workspaceFingerprint",
        "executionProjectId",
        "generation",
        "version",
        "mcpVersion",
    )
    return all(existing.get(key) == payload.get(key) for key in keys)


def _atomic_replace(source: Path, destination: Path, *, retries: int = 8) -> None:
    """Replace destination with source, retrying transient Windows file locks."""
    last_error: OSError | None = None
    for attempt in range(retries):
        try:
            source.replace(destination)
            return
        except OSError as exc:
            last_error = exc
            locked = getattr(exc, "winerror", None) == 32 or exc.errno in {13, 16, 32}
            if not locked or attempt >= retries - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


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
    started_at = _parse_started_at(payload.get("startedAt"))
    if not _pid_matches_lease(pid, started_at):
        status = "pid_reused" if _pid_alive(pid) else "stale"
        return RuntimeBindingStatus(False, status)

    active_root = str(payload.get("workspaceRoot") or "") or None
    if active_root and Path(active_root).resolve() != root:
        return RuntimeBindingStatus(False, "workspace_mismatch")

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
    if generation and configured_generations and generation not in configured_generations:
        return RuntimeBindingStatus(
            False, "generation_mismatch", instance, generation, active_fingerprint, active_project, source
        )

    return RuntimeBindingStatus(
        True, "verified", instance, generation, active_fingerprint, active_project, source
    )
