from __future__ import annotations

from pathlib import Path

from hydracept.cli.json_file import read_json_file
from hydracept.cli.run_facade import parse_input_argument


def test_read_json_file_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "extract.json"
    path.write_bytes(
        b'\xef\xbb\xbf{"document": "Invoice 42", "schema": {"type": "object"}}'
    )
    payload = read_json_file(path)
    assert payload["document"] == "Invoice 42"
    assert payload["schema"]["type"] == "object"


def test_read_json_file_accepts_utf16_le_powershell_outfile(tmp_path: Path) -> None:
    path = tmp_path / "extract.json"
    path.write_bytes('{"document": "Invoice 42", "schema": {"type": "object"}}'.encode("utf-16"))
    payload = parse_input_argument(None, path)
    assert payload["document"] == "Invoice 42"


def test_parse_input_argument_reads_extraction_shape(tmp_path: Path) -> None:
    path = tmp_path / "extract.json"
    path.write_text(
        '{"document": "invoice 42", "schema": {"type": "object", "properties": {"id": {"type": "string"}}}}',
        encoding="utf-8",
    )
    payload = parse_input_argument(None, path)
    assert payload["document"] == "invoice 42"
    assert payload["schema"]["properties"]["id"]["type"] == "string"
    assert parse_input_argument('{"prompt": "x"}', None) == {"prompt": "x"}
