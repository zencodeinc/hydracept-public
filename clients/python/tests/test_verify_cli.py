"""Offline hydracept verify structural checks."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.verify import (
    all_passed,
    format_checks,
    is_manifest,
    load_document,
    structural_lockfile_checks,
    structural_manifest_checks,
)


def test_lockfile_structural_pass(tmp_path: Path) -> None:
    path = tmp_path / "hydracept.lock"
    path.write_text(
        """
kind: hydracept.lock
inference:
  provider: openai
  model: gpt-5.6-sol
  api: responses
  protocol: rip-v1
semantics:
  stateless: true
  fallback: false
  rewriting: false
""",
        encoding="utf-8",
    )
    document = load_document(path)
    assert not is_manifest(path, document)
    checks = structural_lockfile_checks(document)
    assert all_passed(checks)
    rendered = format_checks(checks)
    assert "model pin" in rendered
    assert "native api" in rendered


def test_manifest_filename_and_fallback(tmp_path: Path) -> None:
    path = tmp_path / "run-003.manifest.json"
    path.write_text(
        """
{
  "kind": "hydracept.run-manifest",
  "label": "Experiment 003",
  "receipts": [
    {"receipt_id": "rcpt_a", "fallback": false},
    {"receipt_id": "rcpt_b", "fallback": true}
  ]
}
""",
        encoding="utf-8",
    )
    document = load_document(path)
    assert is_manifest(path, document)
    checks = structural_manifest_checks(document)
    assert any(item["name"] == "no_fallback" and not item["passed"] for item in checks)
    assert not all_passed(checks)
