"""Installed CLI entrypoint with compatibility options for machine-readable commands.

Several public commands have always emitted JSON but historically rejected an
explicit ``--json`` flag. Agents should not need command-specific knowledge to
know when the flag is syntactically accepted. This adapter adds an ignored
``--json`` option only to commands whose existing output is already JSON; it does
not introduce a second renderer or alter execution semantics.

The adapter also repairs the public ``capabilities find`` surface. ``main.py``
contains legacy duplicate registrations for that command; the installed command
is normalized here to one compact, workspace-aware finder without disturbing
lower-level compatibility callbacks.

The adapter also dispatches ``verify <file.png>`` to the local PNG transparency
verifier while preserving the existing lockfile/run-manifest verify callback.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable

import click
import httpx
from typer.main import get_command

from hydracept.cli.main import app as _typer_app

# Paths are intentionally limited to commands whose callbacks already emit JSON.
# Commands that have a real --json/--no-json presentation switch are left alone.
_JSON_COMPAT_PATHS: tuple[tuple[str, ...], ...] = (
    ("health",),
    ("capabilities", "find"),
    ("capabilities", "estimate"),
    ("capabilities", "invoke"),
    ("capability-request", "create"),
    ("capability-request", "show"),
    ("capability-request", "submit"),
    ("jobs", "list"),
    ("jobs", "submit"),
    ("jobs", "get"),
    ("jobs", "receipt"),
    ("jobs", "cancel"),
    ("pinned", "run"),
    ("pinned", "get"),
)

# image.generate.v1 routinely exceeds the old 90-second local wait while
# remaining healthy. This is the CLI projection of the 0.3.12 SmokeWaitPolicy;
# the remote job is never cancelled when the local wait ends.
_IMAGE_SMOKE_TIMEOUT_SECONDS = 300


def _command_map(command: Any) -> dict[str, Any] | None:
    # Typer 0.27 vendors Click (`typer._click`). TyperGroup is not a
    # `click.Group` subclass, so walk the instance command map instead of
    # using isinstance(click.Group).
    commands = getattr(command, "commands", None)
    return commands if isinstance(commands, dict) else None


def _resolve_command(root: Any, path: Iterable[str]) -> Any | None:
    current = root
    for segment in path:
        commands = _command_map(current)
        if commands is None:
            return None
        current = commands.get(segment)
        if current is None:
            return None
    return current


def _has_option(command: Any, option: str) -> bool:
    return any(
        option in (getattr(param, "opts", None) or [])
        for param in getattr(command, "params", [])
    )


def _compat_json_option() -> Any:
    help_text = "Machine-readable output (already the default for this command)."
    try:
        from typer.core import TyperOption

        return TyperOption(
            param_decls=["--json"],
            is_flag=True,
            expose_value=False,
            help=help_text,
        )
    except Exception:
        return click.Option(
            ["--json"],
            is_flag=True,
            expose_value=False,
            help=help_text,
        )


def _add_json_compat(command: Any) -> None:
    if _has_option(command, "--json"):
        return
    command.params.append(_compat_json_option())


def _apply_smoke_wait_policy(root: Any) -> None:
    """Set the installed default without overriding an explicit CLI value."""
    command = _resolve_command(root, ("smoke",))
    if command is None:
        return
    for param in getattr(command, "params", []):
        opts = getattr(param, "opts", None) or []
        if "--poll-seconds" in opts:
            param.default = _IMAGE_SMOKE_TIMEOUT_SECONDS
            break


def _find_headers(api: str) -> dict[str, str]:
    """Use workspace auth only for its bound API origin."""
    try:
        from hydracept.cli.workspace import resolve_workspace

        workspace = resolve_workspace(Path.cwd())
    except Exception:  # noqa: BLE001
        workspace = None
    if workspace is None:
        return {}
    bound_api = str(getattr(workspace, "api_url", "") or "").rstrip("/")
    if not bound_api or bound_api != api.rstrip("/"):
        return {}
    token = str(getattr(workspace, "token", "") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _compact_capability(item: dict[str, Any]) -> dict[str, Any]:
    runnable = item.get("workspaceRunnable")
    workspace = runnable if isinstance(runnable, dict) else {}
    pricing = item.get("pricing")
    price = pricing if isinstance(pricing, dict) else {}
    compact: dict[str, Any] = {
        "key": item.get("key"),
        "title": item.get("title"),
        "runnable": workspace.get("runnable"),
        "status": workspace.get("status"),
        "readySummary": item.get("readySummary"),
    }
    if workspace.get("billingMode") is not None:
        compact["billingMode"] = workspace.get("billingMode")
    if price:
        compact["pricing"] = {
            key: price.get(key)
            for key in ("mode", "estimateRequired", "pricingContext")
            if price.get(key) is not None
        }
    return compact


def _add_capabilities_find_dispatch(root: Any) -> None:
    command = _resolve_command(root, ("capabilities", "find"))
    if command is None:
        return

    def callback(*args: Any, **kwargs: Any) -> None:
        del args
        query = str(kwargs.get("query") or kwargs.get("intent") or "").strip()
        api = str(kwargs.get("api") or "https://api.hydracept.com").rstrip("/")
        response = httpx.get(
            f"{api}/v1/capabilities",
            params={"q": query},
            headers=_find_headers(api),
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("capabilities") if isinstance(payload, dict) else []
        candidates = [
            _compact_capability(item)
            for item in (items or [])[:5]
            if isinstance(item, dict)
        ]
        click.echo(
            json.dumps(
                {
                    "query": query,
                    "candidates": candidates,
                    "count": len(candidates),
                    "execution": "python -m hydracept run <key> --input <json-or-prompt> --json",
                },
                separators=(",", ":"),
            )
        )

    command.callback = callback


def _add_png_verify_dispatch(root: click.Command) -> None:
    command = _resolve_command(root, ("verify",))
    if command is None or command.callback is None:
        return
    original: Callable[..., Any] = command.callback

    # TyperCommand.invoke calls `ctx.invoke(callback, **ctx.params)`. Keep
    # *args/**kwargs so this adapter stays stable across Typer/Click internals.
    # Path parameters may arrive as raw strings; normalize before suffix checks.
    def callback(*args: Any, **kwargs: Any) -> Any:
        path = kwargs.get("path")
        target = Path(path) if path is not None else None
        if target is not None and target.suffix.lower() == ".png":
            from hydracept.cli.artifact_verify import verify_png_cli

            return verify_png_cli(target, json_output=bool(kwargs.get("json_output")))
        return original(*args, **kwargs)

    command.callback = callback


def build_app() -> click.Command:
    root = get_command(_typer_app)
    for path in _JSON_COMPAT_PATHS:
        command = _resolve_command(root, path)
        if command is not None:
            _add_json_compat(command)
    _apply_smoke_wait_policy(root)
    _add_capabilities_find_dispatch(root)
    _add_png_verify_dispatch(root)
    return root


# Click Commands are callable and are valid setuptools console-script entrypoints.
app = build_app()