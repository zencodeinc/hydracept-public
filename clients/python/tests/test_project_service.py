"""Login-persistent project up service (OS task / unit), not a Cursor shell."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.project_service import (
    ProjectUpServiceSpec,
    persist_project_up_workspace,
    service_id,
    write_wrapper_script,
)
from hydracept.cli.project_service_windows import _task_xml, logon_run_command, write_hidden_launcher
from hydracept.cli.project_up_lock import ProjectUpLock, ProjectUpLockError
from hydracept.cli.workspace import read_json, secrets_path


def test_wrapper_script_does_not_embed_token(tmp_path: Path) -> None:
    import sys

    root = tmp_path / "game"
    root.mkdir()
    spec = ProjectUpServiceSpec(
        project_root=root,
        api="https://api.hydracept.com",
        project_id="cpr_studio",
        python_executable="C:\\Python313\\python.exe" if sys.platform == "win32" else "/usr/bin/python3",
    )
    path = write_wrapper_script(spec)
    text = path.read_text(encoding="utf-8")
    assert "pre-coloc" not in text
    assert "--token" not in text
    assert " -m " in text or "'-m'" in text
    assert "hydracept" in text
    assert "project" in text
    assert "up" in text
    assert str(root.resolve()) in text
    assert "https://api.hydracept.com" in text
    assert "cpr_studio" in text
    if sys.platform == "win32":
        assert path.suffix == ".cmd"
        assert ":loop" in text
        assert "goto loop" in text
    else:
        assert path.suffix == ".sh"
        assert "exec " in text


def test_persist_workspace_stores_api_project_and_secret(tmp_path: Path) -> None:
    root = tmp_path / "game"
    root.mkdir()
    persist_project_up_workspace(
        root,
        api="https://api.hydracept.com",
        project_id="cpr_studio",
        token="hapt_secret",
    )
    binding = read_json(root / ".hydracept" / "project.json")
    secrets = read_json(secrets_path(root))
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert binding["apiOrigin"] == "https://api.hydracept.com"
    assert binding["projectId"] == "cpr_studio"
    assert secrets["apiKey"] == "hapt_secret"
    assert ".hydracept/project-up.cmd" in gitignore
    assert ".hydracept/project-up-launch.vbs" in gitignore


def test_service_id_is_stable_for_the_same_checkout(tmp_path: Path) -> None:
    root = tmp_path / "game"
    root.mkdir()
    assert service_id(root) == service_id(root.resolve())
    assert service_id(root).startswith("HydraceptProjectUp-")


def test_windows_task_xml_restarts_on_failure(tmp_path: Path) -> None:
    wrapper = tmp_path / "project-up.cmd"
    xml = _task_xml("HydraceptProjectUp-abc", wrapper)
    assert "RestartOnFailure" in xml
    assert "LogonTrigger" in xml
    assert "PT0S" in xml
    assert str(wrapper) in xml


def test_hidden_launcher_and_run_key_do_not_embed_token(tmp_path: Path) -> None:
    wrapper = tmp_path / "project-up.cmd"
    wrapper.write_text("@echo off\r\n", encoding="utf-8")
    launcher = write_hidden_launcher(wrapper)
    command = logon_run_command(launcher)
    text = launcher.read_text(encoding="ascii")
    assert "--token" not in text
    assert "pre-coloc" not in text
    assert "cmd.exe /c" in text
    assert str(wrapper.resolve()) in text
    assert command.startswith("wscript.exe ")
    assert str(launcher.resolve()) in command


def test_pid_is_alive_for_self() -> None:
    import os

    from hydracept.cli.project_up_lock import pid_is_alive

    assert pid_is_alive(os.getpid())
    assert not pid_is_alive(999_999_999)


def test_project_up_lock_rejects_a_second_holder(tmp_path: Path) -> None:
    root = tmp_path / "game"
    root.mkdir()
    first = ProjectUpLock(root)
    first.acquire()
    try:
        second = ProjectUpLock(root)
        try:
            second.acquire()
            raise AssertionError("second lock should fail")
        except ProjectUpLockError:
            pass
    finally:
        first.release()
    third = ProjectUpLock(root)
    third.acquire()
    third.release()
