"""systemd --user and launchd backends for `project up`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from hydracept.cli.project_service import (
    ProjectServiceError,
    ProjectUpServiceSpec,
    ProjectUpServiceStatus,
    service_id,
    write_wrapper_script,
)


class PosixProjectUpService:
    def install(self, spec: ProjectUpServiceSpec) -> ProjectUpServiceStatus:
        wrapper = write_wrapper_script(spec)
        name = service_id(spec.project_root)
        if sys.platform == "darwin":
            _install_launchd(name, wrapper)
        else:
            _install_systemd(name, wrapper, spec.project_root.resolve())
        self.start(spec.project_root)
        return self.status(spec.project_root)

    def uninstall(self, project_root: Path) -> None:
        name = service_id(project_root)
        if sys.platform == "darwin":
            plist = _launchd_plist(name)
            subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
            plist.unlink(missing_ok=True)
            return
        unit = _systemd_unit(name)
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", unit.name],
            check=False,
            capture_output=True,
        )
        unit.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)

    def status(self, project_root: Path) -> ProjectUpServiceStatus:
        name = service_id(project_root)
        if sys.platform == "darwin":
            result = subprocess.run(
                ["launchctl", "list", name],
                capture_output=True,
                text=True,
                check=False,
            )
            installed = _launchd_plist(name).is_file()
            running = result.returncode == 0
            return ProjectUpServiceStatus(
                name=name,
                installed=installed,
                running=running,
                detail="running" if running else ("installed" if installed else "not installed"),
            )
        unit = _systemd_unit(name)
        installed = unit.is_file()
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit.name],
            capture_output=True,
            text=True,
            check=False,
        )
        running = (result.stdout or "").strip() == "active"
        return ProjectUpServiceStatus(
            name=name,
            installed=installed,
            running=running,
            detail=(result.stdout or "").strip() or ("installed" if installed else "not installed"),
        )

    def start(self, project_root: Path) -> None:
        name = service_id(project_root)
        if sys.platform == "darwin":
            result = subprocess.run(
                ["launchctl", "load", "-w", str(_launchd_plist(name))],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0 and "already loaded" not in (result.stderr or "").lower():
                raise ProjectServiceError((result.stderr or result.stdout or "launchctl load failed").strip())
            return
        result = subprocess.run(
            ["systemctl", "--user", "enable", "--now", _systemd_unit(name).name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ProjectServiceError((result.stderr or result.stdout or "systemctl enable failed").strip())


def _launchd_plist(name: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.hydracept.{name}.plist"


def _systemd_unit(name: str) -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{name}.service"


def _install_launchd(name: str, wrapper: Path) -> None:
    plist = _launchd_plist(name)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                '<plist version="1.0"><dict>',
                "<key>Label</key>",
                f"<string>{name}</string>",
                "<key>ProgramArguments</key>",
                f"<array><string>{wrapper}</string></array>",
                "<key>RunAtLoad</key><true/>",
                "<key>KeepAlive</key><true/>",
                f"<key>WorkingDirectory</key><string>{wrapper.parent.parent}</string>",
                "</dict></plist>",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _install_systemd(name: str, wrapper: Path, project_root: Path) -> None:
    unit = _systemd_unit(name)
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Hydracept project up",
                "After=network-online.target",
                "",
                "[Service]",
                "Type=simple",
                f"WorkingDirectory={project_root}",
                f"ExecStart={wrapper}",
                "Restart=always",
                "RestartSec=15",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProjectServiceError((result.stderr or result.stdout or "systemctl daemon-reload failed").strip())
