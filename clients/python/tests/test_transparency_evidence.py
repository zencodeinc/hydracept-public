"""Agent-facing PNG transparency evidence and CLI verification."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydracept.cli.artifact_verify import verify_png_payload
from hydracept.cli.entrypoint import _resolve_command, app
from hydracept.cli.main import verify_cmd
from hydracept.cli.smoke_contract import evaluate_image_smoke_contract
from hydracept.cli.smoke_runner import SmokeResult
from hydracept.png_alpha import inspect_png_transparency, png_transparency_report


def _rgba_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])
    compressed = zlib.compress(bytes(raw), level=9)

    def chunk(name: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + name
            + body
            + struct.pack(">I", zlib.crc32(name + body) & 0xFFFFFFFF)
        )

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def _transparent_sprite() -> bytes:
    width = height = 16
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            inside = 4 <= x < 12 and 4 <= y < 12
            pixels.append((80, 120, 200, 255) if inside else (0, 0, 0, 0))
    return _rgba_png(width, height, pixels)


def test_transparency_report_preserves_inspector_evidence() -> None:
    report = png_transparency_report(inspect_png_transparency(_transparent_sprite()))

    assert report["schemaVersion"] == "hydracept.png-transparency.v1"
    assert report["verdict"] == "valid_transparent_sprite"
    assert report["hasAlphaChannel"] is True
    assert report["transparentPixelRatio"] == pytest.approx(0.75)
    assert report["opaqueCornerCount"] == 0
    assert report["chromaPlateRatio"] == 0.0
    assert "preview" in report["agentNote"].lower()
    assert "matte" in report["agentNote"].lower()


def test_smoke_contract_and_result_surface_transparency_report() -> None:
    png = _transparent_sprite()
    receipt = {
        "artifacts": [{"id": "art_test", "sha256": hashlib.sha256(png).hexdigest()}],
        "pricing": {"charge": {"customerCharge": {"amountMicros": 44000, "currency": "USD"}}},
    }
    checks = evaluate_image_smoke_contract(receipt, artifact_id="art_test", data=png)
    assert checks["transparency_ok"] is True
    assert checks["transparency_report"]["verdict"] == "valid_transparent_sprite"

    result = SmokeResult(
        job_id="wfr_test",
        status="succeeded",
        receipt=receipt,
        artifact_ids=["art_test"],
        sha256_ok=True,
        transparency_ok=True,
        transparency_report=checks["transparency_report"],
        pricing_ok=True,
    )
    payload = result.to_json()
    assert payload["transparencyOk"] is True
    assert payload["transparencyReport"]["transparentPixelRatio"] == pytest.approx(0.75)
    assert payload["validation"]["transparencyReport"] == payload["transparencyReport"]


def test_verify_png_payload_fails_opaque_png(tmp_path: Path) -> None:
    opaque = _rgba_png(8, 8, [(20, 40, 60, 255)] * 64)
    path = tmp_path / "opaque.png"
    path.write_bytes(opaque)

    payload = verify_png_payload(path)
    assert payload["passed"] is False
    assert payload["transparencyOk"] is False
    assert payload["transparencyReport"]["verdict"] == "invalid_transparency"
    assert "fully opaque" in payload["transparencyReport"]["error"]


def test_entrypoint_resolves_verify_across_typer_click_split() -> None:
    command = _resolve_command(app, ("verify",))
    assert command is not None
    assert command.callback is not None
    assert command.callback is not verify_cmd


def test_canonical_verify_command_dispatches_png_json(tmp_path: Path) -> None:
    path = tmp_path / "sprite.png"
    path.write_bytes(_transparent_sprite())
    result = CliRunner().invoke(app, ["verify", str(path), "--json"])
    assert result.exit_code == 0, f"output={result.output!r} exception={result.exception!r}"
    payload = json.loads(result.output)
    assert payload["schemaVersion"] == "hydracept.cli.png-transparency.v1"
    assert payload["kind"] == "png_transparency"
    assert payload["passed"] is True
    assert payload["transparencyReport"]["verdict"] == "valid_transparent_sprite"
