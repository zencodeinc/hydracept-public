"""Windows-safe Rich console setup for the public CLI."""

from __future__ import annotations

import os
import sys

from rich.console import Console

_STDIO_CONFIGURED = False


def _stream_needs_utf8(stream: object) -> bool:
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return True
    normalized = encoding.lower().replace("-", "")
    return normalized not in ("utf8", "utf16", "utf32")


def configure_stdio_utf8() -> None:
    """Reconfigure stdout/stderr to UTF-8 and line-buffer so poll lines appear on Windows."""
    global _STDIO_CONFIGURED
    if _STDIO_CONFIGURED:
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
    _STDIO_CONFIGURED = True


def cli_console() -> Console:
    configure_stdio_utf8()
    return Console()
