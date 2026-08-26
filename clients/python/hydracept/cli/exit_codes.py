"""Stable CLI exit codes for automation (ADR-019)."""

from __future__ import annotations

SUCCESS = 0
USAGE = 2
AUTH = 3
NOT_READY = 4
CONNECTIVITY = 5
DOCTOR_FAILED = 6
SMOKE_FAILED = 7
