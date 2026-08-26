"""Public project-agent loop: sync authority, watch and execute locally.

Does not import private hydracept_project_sdk. Named operations run from
tools/hydracept/manifest.json argv lists (no shell). Host validate runs the
commands declared in project.yaml.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from hydracept.cli.session_client import SessionClientError, fetch_session_context
from hydracept.cli.workspace import CliOverrides, resolve_workspace

_COMMAND_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")
_SHELLISH = re.compile(r"[;|&`$<>\n]")
_HOST_COMMANDS = frozenset({"validate"})
AGENT_ID = "hydracept-cli"


class ProjectAgentError(Exception):
    """Local project-agent failure (missing files, refused command, bad output)."""


def hydracept_root(project_root: Path) -> Path:
    return Path(project_root) / "tools" / "hydracept"


def resolve_bound_project_id(
    project_root: Path,
    *,
    token: str | None = None,
    project: str | None = None,
) -> str:
    """Hydracept customer project id from login/config, not the yaml slug."""
    explicit = (project or "").strip()
    if explicit:
        return explicit
    session_context: dict[str, Any] | None = None
    try:
        session_context = fetch_session_context()
    except SessionClientError:
        session_context = None
    workspace = resolve_workspace(
        project_root,
        overrides=CliOverrides(token=token, session_context=session_context),
    )
    bound = (workspace.project_id if workspace else "") or ""
    if bound.strip():
        return bound.strip()
    raise ProjectAgentError(
        "No Hydracept project id. Run python -m hydracept login, or pass --project."
    )


def load_project_yaml(project_root: Path) -> dict[str, Any]:
    path = hydracept_root(project_root) / "project.yaml"
    if not path.is_file():
        raise ProjectAgentError(f"Missing {path}. Expected tools/hydracept/project.yaml.")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProjectAgentError(f"Invalid project.yaml: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProjectAgentError("project.yaml must be a mapping")
    return payload


def operations_policy_from_manifest(project_root: Path) -> dict[str, list[str]]:
    """Fail-closed allowlisted names only. Argv never leaves the checkout."""
    path = hydracept_root(project_root) / "manifest.json"
    if not path.is_file():
        return {"allowlisted": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"allowlisted": []}
    if not isinstance(payload, dict):
        return {"allowlisted": []}
    raw = payload.get("operations")
    names: set[str] = set()
    if isinstance(raw, dict):
        for key, spec in raw.items():
            if not isinstance(spec, dict) or spec.get("allowlisted") is not True:
                continue
            command = _declared_command(spec.get("command") or key)
            if command is not None:
                names.add(command)
    return {"allowlisted": sorted(names)}


def build_sync_payload(
    project_root: Path,
    *,
    hydracept_project_id: str,
    repository_revision: str | None = None,
) -> dict[str, Any]:
    """Bind this checkout to the Hydracept project the human is using in Studio."""
    manifest = dict(load_project_yaml(project_root))
    local_slug = str(manifest.get("projectId") or "").strip()
    manifest["projectId"] = hydracept_project_id
    encoded = json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")
    adapter = manifest.get("adapter") if isinstance(manifest.get("adapter"), dict) else {}
    protocol = adapter.get("protocolVersion") if isinstance(adapter, dict) else 1
    return {
        "manifest": manifest,
        "assets": [],
        "profiles": [],
        "repositoryRevision": repository_revision or git_revision(project_root),
        "adapterVersion": str(protocol or 1),
        "manifestHash": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        "operationsPolicy": operations_policy_from_manifest(project_root),
        "localProjectSlug": local_slug,
    }


def git_revision(project_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "local"
    if completed.returncode != 0:
        return "local"
    return (completed.stdout or "").strip() or "local"


def run_named_operation(project_root: Path, command: str, operation_input: dict[str, Any]) -> dict[str, Any]:
    spec = _load_operation_specs(project_root).get(command)
    if spec is None or spec.get("allowlisted") is not True:
        raise ProjectAgentError(f"Local agent does not implement command '{command}'")
    argv = spec.get("argv")
    if not isinstance(argv, list) or not argv:
        raise ProjectAgentError(f"Operation '{command}' is missing a token argv list")
    tokens: list[str] = []
    for item in argv:
        if not isinstance(item, str) or not item.strip():
            raise ProjectAgentError(f"Operation '{command}' argv must be non-empty strings")
        if _SHELLISH.search(item):
            raise ProjectAgentError(f"Operation '{command}' argv looks like shell, not a named program")
        tokens.append(item)
    tokens[0] = _resolve_program(tokens[0])
    env = os.environ.copy()
    env["HYDRACEPT_OPERATION_INPUT"] = json.dumps(operation_input)
    completed = subprocess.run(
        tokens,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        env=env,
    )
    payload = _parse_tool_stdout(completed.stdout)
    if completed.returncode != 0 and payload.get("status") != "failed":
        err = (completed.stderr or completed.stdout or f"exit {completed.returncode}").strip()
        payload = {
            "status": "failed",
            "message": err[-2000:] or f"Operation '{command}' failed",
            "details": {"statusFields": [{"label": "Error", "value": err[-240:] or "failed"}]},
        }
    return payload


def run_validate(project_root: Path) -> list[dict[str, Any]]:
    manifest = load_project_yaml(project_root)
    validation = manifest.get("validation") if isinstance(manifest.get("validation"), dict) else {}
    commands = validation.get("commands") if isinstance(validation, dict) else []
    if not isinstance(commands, list):
        commands = []
    results: list[dict[str, Any]] = []
    for command in commands:
        if not isinstance(command, str) or not command.strip():
            continue
        completed = subprocess.run(
            command,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        results.append(
            {
                "command": command,
                "passed": completed.returncode == 0,
                "exitCode": completed.returncode,
                "stdout": (completed.stdout or "")[-2000:],
                "stderr": (completed.stderr or "")[-2000:],
            }
        )
    return results


def build_operation_report(
    *,
    project_id: str,
    operation_id: str,
    command: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    status = str(payload.get("status") or "failed")
    ok = status == "succeeded"
    status_fields = (
        _status_fields(payload.get("statusFields"))
        or _status_fields(details.get("statusFields"))
        or _status_fields(details.get("status"))
    )
    table = payload.get("table") if payload.get("table") is not None else details.get("table")
    return {
        "schemaVersion": "hydracept.agent-report.v1",
        "agentId": AGENT_ID,
        "projectId": project_id,
        "kind": command,
        "status": "succeeded" if ok else "failed",
        "operationRequestId": operation_id,
        "repositoryRevisionAfter": "local",
        "validationResults": [],
        "errors": [] if ok else [str(payload.get("message") or f"{command} failed")],
        "metrics": {"statusFields": status_fields, "table": table},
        "message": payload.get("message") or "",
        "details": details,
        "statusFields": status_fields,
        "table": table,
    }


def build_validate_report(
    *,
    project_id: str,
    operation_id: str,
    validation_results: list[dict[str, Any]],
) -> dict[str, Any]:
    ok = bool(validation_results) and all(bool(item.get("passed")) for item in validation_results)
    return {
        "schemaVersion": "hydracept.agent-report.v1",
        "agentId": AGENT_ID,
        "projectId": project_id,
        "kind": "validate",
        "status": "succeeded" if ok else "failed",
        "operationRequestId": operation_id,
        "repositoryRevisionAfter": "local",
        "validationResults": validation_results,
        "errors": [] if ok else ["validation failed"],
        "metrics": {},
        "message": "",
        "details": {},
        "statusFields": [],
        "table": None,
    }


def execute_requested_operation(project_root: Path, operation: dict[str, Any]) -> dict[str, Any]:
    command = str(operation.get("command") or "")
    operation_id = str(operation.get("id") or "")
    project_id = str(operation.get("projectId") or "")
    if command == "validate":
        return build_validate_report(
            project_id=project_id,
            operation_id=operation_id,
            validation_results=run_validate(project_root),
        )
    payload = run_named_operation(
        project_root,
        command,
        dict(operation.get("input") or {}),
    )
    return build_operation_report(
        project_id=project_id,
        operation_id=operation_id,
        command=command,
        payload=payload,
    )


def _declared_command(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    command = value.strip()
    if not _COMMAND_NAME.fullmatch(command):
        return None
    if command in _HOST_COMMANDS:
        return None
    return command


def _load_operation_specs(project_root: Path) -> dict[str, dict[str, Any]]:
    path = hydracept_root(project_root) / "manifest.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectAgentError(f"Invalid operation manifest: {exc}") from exc
    raw = payload.get("operations")
    if not isinstance(raw, dict):
        return {}
    specs: dict[str, dict[str, Any]] = {}
    for key, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        command = str(spec.get("command") or key).strip()
        if not _COMMAND_NAME.fullmatch(command):
            continue
        specs[command] = spec
    return specs


def _resolve_program(token: str) -> str:
    if token in {"python", "python3"}:
        return sys.executable
    resolved = shutil.which(token)
    return resolved or token


def _parse_tool_stdout(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {"status": "failed", "message": "Operation produced no output", "details": {}}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {"status": "failed", "message": "Operation output was not JSON", "details": {}}
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        return {"status": "failed", "message": "Operation output was not an object", "details": {}}
    last = payload.get("lastResult") if isinstance(payload.get("lastResult"), dict) else payload
    details = last.get("details") if isinstance(last.get("details"), dict) else {}
    status_fields = (
        _status_fields(details.get("statusFields"))
        or _status_fields(details.get("status"))
        or _status_fields(payload.get("statusFields"))
        or _status_fields(payload.get("status"))
    )
    status = last.get("status")
    if not isinstance(status, str):
        status = "succeeded"
    message = last.get("message") or payload.get("message") or ""
    merged_details = dict(details)
    if status_fields and "statusFields" not in merged_details:
        merged_details["statusFields"] = status_fields
    table = details.get("table") or payload.get("table")
    if table is not None:
        merged_details["table"] = table
    values = details.get("values") if isinstance(details.get("values"), dict) else payload.get("values")
    if isinstance(values, dict):
        merged_details["values"] = values
    return {
        "status": status,
        "message": str(message),
        "details": merged_details,
        "statusFields": status_fields,
        "table": table,
    }


def _status_fields(value: object) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
