"""CLI credential copy must be explicit and never mix machine-output formats."""

from typer.testing import CliRunner

from hydracept.cli import keys_cmd


def _stub_auth(monkeypatch):
    monkeypatch.setattr(keys_cmd, "load_session", lambda: object())
    monkeypatch.setattr(
        keys_cmd, "read_workspace_json",
        lambda path: {"projectId": "cpr_example", "environment": "development"},
    )
    monkeypatch.setattr(
        keys_cmd, "create_key",
        lambda **kwargs: {
            "keyId": "key_example",
            "apiKey": "hydracept_secret_fixture",
            "prefix": "hydracept_secret",
            "projectId": kwargs["project_id"],
            "environment": kwargs["environment"],
        },
    )


def test_keys_create_print_env(monkeypatch):
    _stub_auth(monkeypatch)
    result = CliRunner().invoke(keys_cmd.keys_app, ["create", "--name", "Prisma", "--print-env"])
    assert result.exit_code == 0, result.output
    assert "HYDRACEPT_API_KEY=hydracept_secret_fixture" in result.stdout
    assert "HYDRACEPT_PROJECT=cpr_example" in result.stdout
    assert "HYDRACEPT_ENVIRONMENT=development" in result.stdout
    assert "HYDRACEPT_API_URL=https://api.hydracept.com" in result.stdout
    assert "WARNING" in result.stderr


def test_keys_create_print_env_rejects_combined_output_modes(monkeypatch):
    _stub_auth(monkeypatch)
    for flag in ("--json", "--configure"):
        result = CliRunner().invoke(keys_cmd.keys_app, ["create", "--print-env", flag])
        assert result.exit_code != 0
        assert "cannot be combined" in result.output
