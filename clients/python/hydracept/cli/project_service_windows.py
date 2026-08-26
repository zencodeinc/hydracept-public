"""Windows logon-persistent backend for `project up`.

Task Scheduler is preferred (restart-on-failure). Medium-integrity sessions
often cannot create tasks, so we fall back to HKCU Run plus a hidden
ShellExecute start that is a child of explorer — not Cursor.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from hydracept.cli.project_service import (
    ProjectServiceError,
    ProjectUpServiceSpec,
    ProjectUpServiceStatus,
    service_id,
    wrapper_path,
    write_wrapper_script,
)
from hydracept.cli.project_up_lock import pid_is_alive, read_watcher_pid, watcher_running

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class WindowsProjectUpService:
    def install(self, spec: ProjectUpServiceSpec) -> ProjectUpServiceStatus:
        wrapper = write_wrapper_script(spec)
        launcher = write_hidden_launcher(wrapper)
        name = service_id(spec.project_root)
        try:
            xml_path = spec.project_root.resolve() / ".hydracept" / "project-up.xml"
            xml_path.write_text(_task_xml(name, wrapper), encoding="utf-16")
            _schtasks(["/Create", "/TN", name, "/XML", str(xml_path), "/F"])
        except ProjectServiceError as exc:
            if not _is_access_denied(exc):
                raise
            _set_run_key(name, logon_run_command(launcher))
        self.start(spec.project_root)
        return self.status(spec.project_root)

    def uninstall(self, project_root: Path) -> None:
        name = service_id(project_root)
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", name, "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 and not _is_missing_task(result) and not _is_access_denied_text(
            (result.stderr or "") + (result.stdout or "")
        ):
            raise ProjectServiceError(result.stdout.strip() or result.stderr.strip() or "schtasks delete failed")
        _delete_run_key(name)
        _stop_watcher_processes(project_root)

    def status(self, project_root: Path) -> ProjectUpServiceStatus:
        name = service_id(project_root)
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            output = result.stdout or ""
            running = "Running" in output or watcher_running(project_root)
            return ProjectUpServiceStatus(
                name=name,
                installed=True,
                running=running,
                detail="running" if running else "installed",
            )
        installed = _run_key_exists(name)
        running = watcher_running(project_root)
        if not installed:
            return ProjectUpServiceStatus(name=name, installed=False, running=False, detail="not installed")
        return ProjectUpServiceStatus(
            name=name,
            installed=True,
            running=running,
            detail="running" if running else "installed (logon)",
        )

    def start(self, project_root: Path) -> None:
        if watcher_running(project_root):
            return
        name = service_id(project_root)
        try:
            _schtasks(["/Run", "/TN", name])
            return
        except ProjectServiceError as exc:
            if not _is_access_denied(exc) and "cannot find" not in str(exc).lower():
                raise
        launcher = hidden_launcher_path(project_root)
        if not launcher.is_file():
            raise ProjectServiceError(f"missing launcher {launcher}")
        os.startfile(str(launcher))  # noqa: S606 — ShellExecute via explorer, outside Cursor's job


def hidden_launcher_path(project_root: Path) -> Path:
    return Path(project_root).resolve() / ".hydracept" / "project-up-launch.vbs"


def write_hidden_launcher(wrapper: Path) -> Path:
    path = wrapper.with_name("project-up-launch.vbs")
    cmd = str(wrapper.resolve()).replace('"', '""')
    path.write_text(
        "Set sh = CreateObject(\"Wscript.Shell\")\r\n"
        f"sh.Run \"cmd.exe /c \"\"{cmd}\"\"\", 0, False\r\n",
        encoding="ascii",
    )
    return path


def logon_run_command(launcher: Path) -> str:
    return f'wscript.exe "{launcher.resolve()}"'


def _set_run_key(name: str, value: str) -> None:
    import winreg

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def _delete_run_key(name: str) -> None:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        return
    try:
        try:
            winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
    finally:
        winreg.CloseKey(key)


def _run_key_exists(name: str) -> bool:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_QUERY_VALUE)
    except FileNotFoundError:
        return False
    try:
        winreg.QueryValueEx(key, name)
        return True
    except FileNotFoundError:
        return False
    finally:
        winreg.CloseKey(key)


def _stop_watcher_processes(project_root: Path) -> None:
    pid = read_watcher_pid(project_root)
    if pid and pid_is_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    root = str(Path(project_root).resolve())
    marker = str(wrapper_path(project_root))
    script = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.CommandLine -and ("
        f"$_.CommandLine -like '*{ _ps_literal(root) }*project up*' -or "
        f"$_.CommandLine -like '*{ _ps_literal(marker) }*'"
        ") } | ForEach-Object { "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )


def _ps_literal(value: str) -> str:
    return value.replace("'", "''").replace("[", "`[").replace("]", "`]")


def _is_access_denied(exc: BaseException) -> bool:
    return _is_access_denied_text(str(exc))


def _is_access_denied_text(text: str) -> bool:
    lowered = text.lower()
    return "access is denied" in lowered or "0x80070005" in lowered


def _is_missing_task(result: subprocess.CompletedProcess[str]) -> bool:
    blob = f"{result.stderr or ''} {result.stdout or ''}".lower()
    return "cannot find" in blob


def _schtasks(args: list[str]) -> str:
    result = subprocess.run(
        ["schtasks", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "schtasks failed").strip()
        raise ProjectServiceError(message)
    return result.stdout or ""


def _task_xml(name: str, wrapper: Path) -> str:
    command = escape(str(wrapper))
    working = escape(str(wrapper.parent.parent))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{escape(name)} — Hydracept project up</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <WorkingDirectory>{working}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""
