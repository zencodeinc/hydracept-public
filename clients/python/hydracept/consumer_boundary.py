"""Embedded consumer-boundary scanner for the public hydracept CLI."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import yaml

FORBIDDEN_HOSTS = [
    "api.openai.com",
    "api.elevenlabs.io",
    "api.anthropic.com",
]

FORBIDDEN_LEGACY_PATHS = [
    "/v1/visual/jobs",
    "/v1/invocations",
    "POST /v1/jobs",
]

FORBIDDEN_PACKAGE_PATTERNS = [
    re.compile(r"ProjectReference.*Zencode Forge", re.I),
    re.compile(r"file:.*Zencode Forge/clients", re.I),
    re.compile(r"file:.*[/\\]Hydracept[/\\](apps|packages|workers)", re.I),
    re.compile(r"from hydracept_api\b", re.I),
    re.compile(r"import hydracept_api\b", re.I),
    re.compile(r"from forge_api\b", re.I),
    re.compile(r"import forge_api\b", re.I),
    re.compile(r"@zencode/forge-client", re.I),
    re.compile(r"Zencode\.Forge\.Client", re.I),
    re.compile(r"zencode-forge", re.I),
]

LEGACY_STALE_PATTERNS = [
    re.compile(r"Zencode Forge", re.I),
    re.compile(r"\bforge consumer-check\b", re.I),
    re.compile(r"\bforge doctor\b", re.I),
    re.compile(r"\bforge login\b", re.I),
    re.compile(r"forge\.zencode", re.I),
    re.compile(r"\bFORGE_[A-Z0-9_]+\b"),
    re.compile(r"forge-dev-token"),
]

SCAN_EXTENSIONS = {".cs", ".ts", ".tsx", ".js", ".mjs", ".py", ".json", ".csproj"}


def _load_exceptions() -> list[dict]:
    try:
        data_files = resources.files("hydracept.data")
        text = (data_files / "hydracept-consumer-exceptions.yaml").read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        return list(data.get("exceptions") or [])
    except Exception:
        return []


def _expired_exceptions(exceptions: list[dict]) -> list[str]:
    now = datetime.now(timezone.utc).date()
    expired: list[str] = []
    for entry in exceptions:
        expires = entry.get("expires")
        if not expires:
            continue
        try:
            exp_date = datetime.strptime(str(expires), "%Y-%m-%d").date()
        except ValueError:
            expired.append(str(entry))
            continue
        if exp_date < now:
            expired.append(str(entry))
    return expired


def scan(root: Path) -> list[str]:
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        if "node_modules" in path.parts or ".git" in path.parts or "dist" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        for host in FORBIDDEN_HOSTS:
            if host in text:
                violations.append(f"{rel}: direct provider host {host}")
        for legacy_path in FORBIDDEN_LEGACY_PATHS:
            if legacy_path in text:
                violations.append(f"{rel}: legacy API path {legacy_path}")
        for pattern in FORBIDDEN_PACKAGE_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: forbidden package reference ({pattern.pattern})")
        for pattern in LEGACY_STALE_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: legacy Forge branding ({pattern.pattern})")
    return violations


def scan_path(target: Path) -> tuple[int, str]:
    expired = _expired_exceptions(_load_exceptions())
    if expired:
        return 1, "Expired hydracept-consumer-exceptions:\n" + "\n".join(f"  - {e}" for e in expired)
    violations = scan(target)
    if violations:
        detail = "Consumer boundary violations:\n" + "\n".join(f"  - {v}" for v in violations)
        return 1, detail
    return 0, f"Consumer boundary OK ({target})"
