"""Embedded consumer-boundary scanner for the public hydracept CLI.

Exclusions
----------
Files whose root-relative path contains any part in
:data:`EXCLUDED_PATH_PARTS` are skipped. These are generated, vendored,
cached or scratch locations that a consuming product does not author and
therefore cannot be held responsible for. The check is a set intersection on
the path parts rather than a chain of ``if`` conditions, and it uses
root-relative parts so that a checkout which merely *lives* under a skipped
directory name (for example a repo cloned into ``~/bin``) is still scanned.

``.github`` is deliberately **not** excluded: workflow files are authored
configuration that governs how the product integrates, so a violation there
is a real violation.

Classification
--------------
Every reported violation is tagged ``code`` or ``documentation``, appended as
``[tag] (line N)`` after the existing ``rel: message`` prefix. A match is
``documentation`` when it occurs in a prose surface (``*.md``, ``*.rst``,
``*.txt``; scanned by strict mode) or exclusively on comment-only lines of a
source file; otherwise it is ``code``. This is intentionally a plain line/text
heuristic rather than AST analysis: it lets a human or CI policy separate an
informational mention from an executable reference without parsing every
language the scanner sees. If a pattern matches both a comment line and a code
line in the same file, the violation is reported as ``code`` so real
references are never downgraded.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

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

# Prose surfaces, scanned in strict mode. Matches here are tagged
# "documentation" so a textual mention is not confused with an executable
# reference; standard mode stays source-only.
DOCUMENTATION_SUFFIXES = {".md", ".rst", ".txt"}

STRICT_SCAN_EXTENSIONS = (
    SCAN_EXTENSIONS
    | DOCUMENTATION_SUFFIXES
    | {
        ".toml",
        ".yaml",
        ".yml",
        ".xml",
        ".props",
        ".targets",
    }
)

# Path parts that consumers never author or control. Each entry is justified
# inline; anything not listed here (notably ".github") is still scanned.
EXCLUDED_PATH_PARTS = {
    ".hydracept",  # generated Hydracept workspace state (agent-context, secrets, output)
    ".git",  # VCS internals
    "__pycache__",  # Python bytecode cache
    ".venv",  # Python virtualenv
    "venv",  # Python virtualenv (undotted)
    ".mypy_cache",  # mypy type-check cache
    ".pytest_cache",  # pytest cache
    ".ruff_cache",  # ruff cache
    "node_modules",  # JS/TS dependency tree
    "dist",  # common JS/TS build output
    "build",  # common build output
    ".next",  # Next.js build output
    ".turbo",  # Turborepo cache
    "coverage",  # coverage report output
    "out",  # common build output
    "obj",  # .NET intermediate output
    "bin",  # .NET compiled output
}

# Line prefixes that mark a line as a comment in the scanned languages.
COMMENT_PREFIXES = ("#", "//", "/*", "*", "<!--", ";")


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


def _checks() -> list[tuple[str, Any, bool]]:
    """(message, probe, is_regex) for every forbidden pattern, in report order."""
    checks: list[tuple[str, Any, bool]] = []
    for host in FORBIDDEN_HOSTS:
        checks.append((f"direct provider host {host}", host, False))
    for legacy_path in FORBIDDEN_LEGACY_PATHS:
        checks.append((f"legacy API path {legacy_path}", legacy_path, False))
    for pattern in FORBIDDEN_PACKAGE_PATTERNS:
        checks.append((f"forbidden package reference ({pattern.pattern})", pattern, True))
    for pattern in LEGACY_STALE_PATTERNS:
        checks.append((f"legacy Forge branding ({pattern.pattern})", pattern, True))
    return checks


_CHECKS = _checks()


def _probe_matches(probe: Any, is_regex: bool, value: str) -> bool:
    return bool(probe.search(value)) if is_regex else probe in value


def _matching_lines(lines: list[str], probe: Any, is_regex: bool, text: str) -> list[int]:
    hits = [number for number, line in enumerate(lines, 1) if _probe_matches(probe, is_regex, line)]
    if not hits and _probe_matches(probe, is_regex, text):
        # A probe that only matches across lines must still be reported, never lost.
        return [1]
    return hits


def _first_non_comment_line(lines: list[str], probe: Any, is_regex: bool, text: str) -> int | None:
    """First hit that is not on a comment-only line, or ``None``.

    The tag only needs to know whether any hit is code, so scanning can stop as
    soon as one is found instead of collecting every match.
    """
    for number, line in enumerate(lines, 1):
        if not _probe_matches(probe, is_regex, line):
            continue
        if not line.lstrip().startswith(COMMENT_PREFIXES):
            return number
    if not any(_probe_matches(probe, is_regex, line) for line in lines) and _probe_matches(
        probe, is_regex, text
    ):
        # Cross-line match only: report it rather than dropping the violation.
        return 1
    return None


def scan(root: Path, *, strict: bool = False) -> list[str]:
    violations: list[str] = []
    extensions = STRICT_SCAN_EXTENSIONS if strict else SCAN_EXTENSIONS
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        rel_parts = path.relative_to(root).parts
        if EXCLUDED_PATH_PARTS.intersection(rel_parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # One C-level whole-text pass decides which probes are even worth a
        # line-level look; most files match nothing.
        matched = [
            (message, probe, is_regex)
            for message, probe, is_regex in _CHECKS
            if _probe_matches(probe, is_regex, text)
        ]
        if not matched:
            continue
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        lines = text.splitlines()
        for message, probe, is_regex in matched:
            if suffix in DOCUMENTATION_SUFFIXES:
                tag = "documentation"
                hits = _matching_lines(lines, probe, is_regex, text)
            else:
                code_line = _first_non_comment_line(lines, probe, is_regex, text)
                tag = "code" if code_line is not None else "documentation"
                hits = [code_line] if code_line is not None else _matching_lines(
                    lines, probe, is_regex, text
                )
            if not hits:
                continue
            violations.append(f"{rel}: {message} [{tag}] (line {hits[0]})")
    return violations


def scan_tracked_secrets(root: Path) -> list[str]:
    """Detect Hydracept secrets.json tracked by git."""
    violations: list[str] = []
    git_dir = root / ".git"
    if not git_dir.is_dir():
        return violations
    try:
        import subprocess

        result = subprocess.run(
            ["git", "ls-files", "--", ".hydracept/secrets.json", "**/.hydracept/secrets.json"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                violations.append(f"{line}: Hydracept secrets.json must not be committed")
    except Exception:
        pass
    return violations


def scan_path(target: Path, *, strict: bool = False) -> tuple[int, str]:
    expired = _expired_exceptions(_load_exceptions())
    if expired:
        return 1, "Expired hydracept-consumer-exceptions:\n" + "\n".join(
            f"  - {e}" for e in expired
        )
    violations = scan(target, strict=strict) + scan_tracked_secrets(target)
    if violations:
        detail = "Consumer boundary violations:\n" + "\n".join(f"  - {v}" for v in violations)
        return 1, detail
    mode = "strict" if strict else "standard"
    return 0, f"Consumer boundary OK ({target}) [{mode}]"
