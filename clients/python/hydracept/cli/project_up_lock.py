"""Exclusive lock so two project-up watchers cannot share a checkout."""

from __future__ import annotations

import os
import sys
from pathlib import Path


class ProjectUpLockError(Exception):
    """Another project up watcher already holds this checkout."""


class ProjectUpLock:
    def __init__(self, project_root: Path) -> None:
        root = Path(project_root).resolve()
        hydra = root / ".hydracept"
        self.lock_path = hydra / "project-up.lock"
        self.pid_path = hydra / "project-up.pid"
        self._handle = None

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+b")
        try:
            _lock_exclusive(handle)
        except OSError as exc:
            handle.close()
            raise ProjectUpLockError("project up is already running for this checkout") from exc
        self.pid_path.write_text(f"{os.getpid()}\n", encoding="ascii")
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            _unlock(handle)
            self.pid_path.unlink(missing_ok=True)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> ProjectUpLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


def read_watcher_pid(project_root: Path) -> int | None:
    path = Path(project_root).resolve() / ".hydracept" / "project-up.pid"
    try:
        return int(path.read_text(encoding="ascii").strip().splitlines()[0])
    except (OSError, ValueError, IndexError):
        return None


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # Access denied still means the pid exists.
        return ctypes.GetLastError() == 5
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def watcher_running(project_root: Path) -> bool:
    pid = read_watcher_pid(project_root)
    return pid is not None and pid_is_alive(pid)


def _lock_exclusive(handle: object) -> None:
    if sys.platform == "win32":
        import msvcrt

        file_handle = handle  # type: ignore[assignment]
        file_handle.seek(0)
        if file_handle.read(1) == b"":
            file_handle.write(b"\0")
            file_handle.flush()
        file_handle.seek(0)
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[union-attr]


def _unlock(handle: object) -> None:
    if sys.platform == "win32":
        import msvcrt

        file_handle = handle  # type: ignore[assignment]
        file_handle.seek(0)
        try:
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[union-attr]
