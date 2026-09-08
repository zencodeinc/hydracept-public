"""Allow `python -m hydracept` as a PATH-independent CLI entry."""

from __future__ import annotations

from hydracept.cli.entrypoint import app

if __name__ == "__main__":
    app()
