"""Executable authority for the commands advertised to agents.

ADR-034: an agent-facing instruction is a projection of a declared authority, and every
projection has an executable contradiction check. The authority for agent entrypoint
commands is the CLI command registry itself, so this module derives the advertised
command/flag surface by introspecting the real typer app instead of trusting prose in
`agent-context`, `public/docs/*`, `llms.txt`, or plugin manifests.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from hydracept.cli.main import app


def _accepted_flags(command: Any) -> tuple[str, ...]:
    flags: set[str] = set()
    for param in getattr(command, "params", None) or ():
        for option in [
            *(getattr(param, "opts", None) or ()),
            *(getattr(param, "secondary_opts", None) or ()),
        ]:
            if isinstance(option, str) and option.startswith("-"):
                flags.add(option)
    return tuple(sorted(flags))


def _subcommands(command: Any) -> Mapping[str, Any]:
    commands = getattr(command, "commands", None)
    return commands if isinstance(commands, Mapping) else {}


@lru_cache(maxsize=1)
def _registry() -> dict[str, tuple[str, ...]]:
    from typer.main import get_command

    registry: dict[str, tuple[str, ...]] = {}

    def walk(command: Any, path: list[str]) -> None:
        if path:
            registry[" ".join(path)] = _accepted_flags(command)
        for name, child in _subcommands(command).items():
            walk(child, [*path, name])

    for name, child in _subcommands(get_command(app)).items():
        walk(child, [name])
    return registry


def advertised_commands() -> dict[str, tuple[str, ...]]:
    """Map a command path to the option flags it accepts.

    Keys are space-joined command paths, e.g. "init", "init --apply", "mcp serve",
    "jobs submit". Values are the accepted option strings for that command,
    including short and long forms, e.g. ("--apply", "--yes", "--json").
    """
    return dict(_registry())


def command_accepts(command_path: list[str], flags: list[str]) -> bool:
    """True when every flag is accepted by the given command path."""
    if not command_path:
        return False
    accepted = _registry().get(" ".join(command_path))
    if accepted is None:
        return False
    return all(flag in accepted for flag in flags)
