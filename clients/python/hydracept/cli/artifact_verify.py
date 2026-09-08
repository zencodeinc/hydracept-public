"""Local artifact verification for machine-trustable media evidence."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Any

import click

from hydracept.cli.exit_codes import NOT_READY
from hydracept.png_alpha import (
    PngTransparencyError,
    TRANSPARENCY_AGENT_NOTE,
    inspect_png_transparency,
    png_transparency_report,
)

PNG_VERIFY_SCHEMA_VERSION = "hydracept.cli.png-transparency.v1"


def verify_png_payload(path: Path) -> dict[str, Any]:
    """Verify PNG transparency from file bytes, never from a rendered preview."""
    resolved = path.resolve()
    try:
        inspection = inspect_png_transparency(resolved.read_bytes())
    except (OSError, PngTransparencyError, struct.error, zlib.error, IndexError) as exc:
        return {
            "schemaVersion": PNG_VERIFY_SCHEMA_VERSION,
            "path": str(resolved),
            "kind": "png_transparency",
            "passed": False,
            "transparencyOk": False,
            "transparencyReport": {
                "schemaVersion": "hydracept.png-transparency.v1",
                "verdict": "invalid_transparency",
                "error": str(exc),
                "agentNote": TRANSPARENCY_AGENT_NOTE,
            },
        }
    return {
        "schemaVersion": PNG_VERIFY_SCHEMA_VERSION,
        "path": str(resolved),
        "kind": "png_transparency",
        "passed": True,
        "transparencyOk": True,
        "transparencyReport": png_transparency_report(inspection),
    }


def verify_png_cli(path: Path, *, json_output: bool) -> None:
    payload = verify_png_payload(path)
    if json_output:
        click.echo(json.dumps(payload, separators=(",", ":")))
    else:
        report = payload["transparencyReport"]
        if payload["passed"]:
            click.echo("PNG transparency valid")
            click.echo(
                f"alpha=yes transparent={report['transparentPixelRatio']:.1%} "
                f"opaqueCorners={report['opaqueCornerCount']}/4 "
                f"chromaPlate={report['chromaPlateRatio']:.1%}"
            )
            click.echo(report["agentNote"])
        else:
            click.echo(f"PNG transparency invalid: {report['error']}")
    if not payload["passed"]:
        raise click.exceptions.Exit(NOT_READY)
