"""Integration readiness unit tests for hydracept doctor."""

from __future__ import annotations

from hydracept.cli.doctor import (
    DoctorCheck,
    DoctorReport,
    _capability_keys,
    _environment_from_context,
    _project_id_from_context,
    project_alignment_checks,
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


def test_project_alignment_home_mismatch_is_warning() -> None:
    checks = project_alignment_checks(
        "cpr_checkout",
        token_project="cpr_checkout",
        home_project="cpr_home",
    )
    assert len(checks) == 1
    assert checks[0].passed is False
    assert checks[0].fatal is False
    report = DoctorReport()
    report.add(checks[0])
    assert report.passed


def test_project_alignment_token_mismatch_is_fatal() -> None:
    checks = project_alignment_checks(
        "cpr_checkout",
        token_project="cpr_token",
        home_project="cpr_checkout",
    )
    assert checks[0].passed is False
    assert checks[0].fatal is True
    report = DoctorReport()
    report.add(checks[0])
    assert not report.passed


def test_project_alignment_home_echoed_as_token_is_warning() -> None:
    checks = project_alignment_checks(
        "cpr_checkout",
        token_project="cpr_home",
        home_project="cpr_home",
    )
    assert len(checks) == 1
    assert checks[0].passed is False
    assert checks[0].fatal is False
    report = DoctorReport()
    report.add(checks[0])
    assert report.passed
    payload = report.to_json_dict()
    assert payload["failedChecks"] == []
    assert payload["warnings"][0]["name"] == "local.config_project"
