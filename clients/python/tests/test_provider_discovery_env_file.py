"""Provider discovery env-file path resolution."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.provider_discovery import discover_provider


def test_discover_provider_reads_absolute_from_env_file(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "secrets" / "vendor.env"
    outside.parent.mkdir()
    outside.write_text("OPENAI_API_KEY=sk-from-absolute-path\n", encoding="utf-8")

    found = discover_provider("openai", project_root, extra_env_file=outside)
    assert found is not None
    assert found.secret == "sk-from-absolute-path"
    assert found.source == "env_file"
    assert Path(found.source_path) == outside
