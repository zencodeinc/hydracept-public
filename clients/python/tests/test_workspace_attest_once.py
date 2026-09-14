from __future__ import annotations

from pathlib import Path

from hydracept.mcp.workspace_locator import (
    reset_runtime_attestation_cache,
    resolve_mcp_workspace,
)


def test_resolve_mcp_workspace_attests_once_per_process(tmp_path: Path, monkeypatch) -> None:
    reset_runtime_attestation_cache()
    calls = {"n": 0}

    def _attest(root: Path, *, source: str, env: dict[str, str]) -> dict:
        calls["n"] += 1
        return {"workspaceRoot": str(root)}

    monkeypatch.setattr(
        "hydracept.mcp.runtime_binding.attest_runtime_binding",
        _attest,
    )
    env = {"HYDRACEPT_MCP_GENERATION": "gen-test"}
    first = resolve_mcp_workspace(tmp_path, env=env)
    second = resolve_mcp_workspace(tmp_path, env=env)
    assert first == second.resolve()
    assert calls["n"] == 1
