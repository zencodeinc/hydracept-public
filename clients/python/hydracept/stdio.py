"""CLI stdio line-buffering. HydraceptClient does not call this.

Coding-agent shells capture pipes, so Python block-buffers stdout. The public
client wait helpers emit flushed JSON progress instead of mutating global
stdio. This module is for the CLI process only.
"""

from __future__ import annotations

import os
import sys

_CONFIGURED = False


def _stream_needs_utf8(stream: object) -> bool:
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return True
    normalized = encoding.lower().replace("-", "")
    return normalized not in ("utf8", "utf16", "utf32")


def configure_agent_stdio() -> None:
    """Reconfigure stdout/stderr to line-buffered UTF-8 for piped agent shells.

    Python block-buffers when stdout is not a TTY. Coding-agent terminals capture
    pipes, so ``print()`` after ``HydraceptClient(...)`` can sit silent for minutes
    and look like a hang during client initialization.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        kwargs: dict[str, str | bool] = {"line_buffering": True}
        if _stream_needs_utf8(stream):
            kwargs["encoding"] = "utf-8"
            kwargs["errors"] = "replace"
        try:
            reconfigure(**kwargs)
        except (OSError, TypeError, ValueError):
            if _stream_needs_utf8(stream):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    pass
    _CONFIGURED = True
