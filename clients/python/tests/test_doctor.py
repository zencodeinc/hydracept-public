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


def test_doctor_report_includes_identity_and_binding() -> None:
    report = DoctorReport()
    report.add(DoctorCheck("ok", True, "good"))
    report.identity = {
        "status": "ready",
        "provider": "github",
        "account": "jklappstein",
        "authenticated": True,
    }
    report.project_binding = {
        "status": "ready",
        "source": "repository match",
        "environment": "development",
    }
    payload = report.to_json_dict()
    assert payload["identity"]["account"] == "jklappstein"
    assert payload["projectBinding"]["source"] == "repository match"


def test_doctor_report_fails_on_fatal() -> None:
    report = DoctorReport()
    report.add(DoctorCheck("bad", False, "broken"))
    assert not report.passed


def test_project_alignment_home_mismatch_is_informational() -> None:
    checks = project_alignment_checks(
        "cpr_checkout",
        token_project="cpr_checkout",
        home_project="cpr_home",
    )
    names = {check.name: check for check in checks}
    assert names["local.config_project"].passed is True
    assert names["local.config_project"].fatal is False
    assert names["api.account_home_context"].passed is True
    assert names["api.account_home_context"].fatal is False
    assert "informational" in names["api.account_home_context"].detail
    assert "checkout binding remains authoritative" in names["api.account_home_context"].detail
    assert "local.home_project" not in names
    report = DoctorReport()
    for check in checks:
        report.add(check)
    assert report.passed
    payload = report.to_json_dict()
    assert payload["failedChecks"] == []
    assert payload["warnings"] == []
    assert payload["sections"]["project"]["status"] == "ready"


def test_project_alignment_token_mismatch_is_fatal() -> None:
    checks = project_alignment_checks(
        "cpr_checkout",
        token_project="cpr_token",
        home_project="cpr_checkout",
    )
    assert checks[0].passed is False
    assert checks[0].fatal is True
    assert checks[0].name == "local.config_project"
    report = DoctorReport()
    report.add(checks[0])
    assert not report.passed


def test_project_alignment_home_echoed_as_token_is_informational() -> None:
    checks = project_alignment_checks(
        "cpr_checkout",
        token_project="cpr_home",
        home_project="cpr_home",
    )
    names = {check.name: check for check in checks}
    assert names["local.config_project"].passed is True
    assert names["api.account_home_context"].passed is True
    assert names["api.account_home_context"].fatal is False
    assert "local.home_project" not in names
    report = DoctorReport()
    for check in checks:
        report.add(check)
    assert report.passed
    payload = report.to_json_dict()
    assert payload["failedChecks"] == []
    assert payload["warnings"] == []
    assert payload["sections"]["project"]["status"] == "ready"


def test_project_alignment_matching_home_checkout_is_not_fatal() -> None:
    checks = project_alignment_checks(
        "cpr_home",
        token_project="cpr_home",
        home_project="cpr_home",
    )
    names = {check.name: check for check in checks}
    assert names["local.config_project"].passed is True
    assert "api.account_home_context" not in names
    report = DoctorReport()
    for check in checks:
        report.add(check)
    assert report.passed


def test_doctor_sections_expose_semantic_status() -> None:
    report = DoctorReport()
    report.add(DoctorCheck("local.credential", True, "GitHub example-user", bucket="workspace"))
    report.add(
        DoctorCheck(
            "api.managed_trial",
            True,
            "Managed trial remaining $1.00",
            bucket="managedTrial",
        )
    )
    sections = report.sections()
    assert sections["identity"]["status"] == "ready"
    assert sections["managedInference"]["status"] == "ready"
    assert report.to_json_dict()["sections"]["identity"]["detail"] == "GitHub example-user"


def test_doctor_byok_section_is_not_ready_when_only_managed_covers() -> None:
    report = DoctorReport()
    report.add(DoctorCheck("api.image_generation", True, "imageGenerationReady=true", bucket="providers"))
    report.funding = {
        "byokConnected": False,
        "managedExecutionFundingAvailable": True,
    }
    sections = report.sections()
    assert sections["byok"]["status"] == "not_required"
    assert "BYOK not bound" in sections["byok"]["detail"]


def test_doctor_json_warns_when_mcp_reload_required() -> None:
    report = DoctorReport()
    report.add(DoctorCheck("local.credential", True, "ok"))
    report.mcp = {"bound": True, "reloadRequired": True}
    payload = report.to_json_dict()
    assert payload["passed"] is True
    assert any(item["name"] == "mcp.reload" for item in payload["warnings"])


def test_doctor_presents_live_stale_mcp_as_functional() -> None:
    report = DoctorReport()
    report.mcp = {
        "bound": True,
        "reloadRequired": True,
        "readiness": "runtime_reload_available",
        "runtimeStatus": "generation_mismatch",
    }
    assert report.sections()["mcp"] == {
        "status": "ready",
        "detail": "functional; reload available",
    }
