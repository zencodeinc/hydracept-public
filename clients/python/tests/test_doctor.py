"""Integration readiness unit tests for hydracept doctor."""

from __future__ import annotations

from hydracept.cli.doctor import (
    DoctorCheck,
    DoctorReport,
    _capability_keys,
    _environment_from_context,
    _project_id_from_context,
)


def test_capability_keys_from_dict() -> None:
    payload = {"capabilities": [{"key": "image.generate.v1"}, {"key": "text.general.fast.v1"}]}
    assert _capability_keys(payload) == {"image.generate.v1", "text.general.fast.v1"}


def test_capability_keys_from_list() -> None:
    payload = [{"capabilityKey": "audio.sfx.generate.v1"}]
    assert _capability_keys(payload) == {"audio.sfx.generate.v1"}


def test_project_id_from_context() -> None:
    ctx = {"project": {"id": "cpr_abc"}, "environment": {"slug": "development"}}
    assert _project_id_from_context(ctx) == "cpr_abc"
    assert _environment_from_context(ctx) == "development"


def test_doctor_report_passed_with_warnings() -> None:
    report = DoctorReport()
    report.add(DoctorCheck("warn", False, "optional", fatal=False))
    report.add(DoctorCheck("ok", True, "good"))
    assert report.passed


def test_doctor_report_fails_on_fatal() -> None:
    report = DoctorReport()
    report.add(DoctorCheck("bad", False, "broken"))
    assert not report.passed
