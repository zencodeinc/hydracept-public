"""Install Hydracept Agent Pack into coding-agent hosts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hydracept.cli.agents.detect import HOSTS, auto_hosts, detect_host
from hydracept.cli.agents.render import RENDERERS, write_manifest
from hydracept.cli.smoke_runner import SmokeError, run_smoke


@dataclass
class InstallResult:
    hosts: list[str]
    files: list[str]
    smoke: dict[str, Any] | None = None


def install_agent_pack(
    project_root: Path,
    *,
    host: str | None = None,
    auto: bool = False,
    smoke: bool = False,
    repo_root: Path | None = None,
) -> InstallResult:
    targets: list[str]
    if auto:
        targets = auto_hosts(project_root)
        if not targets:
            targets = list(HOSTS)
    elif host:
        targets = [host]
    else:
        raise ValueError("Specify host or --auto")

    written: list[str] = []
    installed_hosts: list[str] = []
    for name in targets:
        if name not in RENDERERS:
            raise ValueError(f"Unknown host: {name}")
        files = RENDERERS[name](project_root, repo_root=repo_root)
        write_manifest(project_root, name, files)
        written.extend(files)
        installed_hosts.append(name)

    from hydracept.cli.mcp_bind import bind_workspace_mcp

    bind = bind_workspace_mcp(project_root)
    written.extend(bind.project_config)

    smoke_result: dict[str, Any] | None = None
    if smoke:
        try:
            result = run_smoke(project_root)
            smoke_result = {
                "jobId": result.job_id,
                "status": result.status,
                "artifactIds": result.artifact_ids,
            }
        except SmokeError as exc:
            smoke_result = {"error": str(exc)}

    return InstallResult(hosts=installed_hosts, files=written, smoke=smoke_result)


def describe_install_targets(project_root: Path, host: str | None, auto: bool) -> dict[str, Any]:
    if auto:
        return {"mode": "auto", "targets": auto_hosts(project_root) or list(HOSTS)}
    if host:
        detection = detect_host(project_root, host)
        return {
            "mode": "explicit",
            "target": host,
            "detected": detection.detected,
            "reason": detection.reason,
        }
    return {"mode": "unset"}
