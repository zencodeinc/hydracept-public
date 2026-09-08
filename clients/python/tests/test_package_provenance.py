"""Package provenance classification tests."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.package_provenance import (
    classify_distribution,
    package_provenance,
    points_at_repository,
)


def test_package_provenance_reports_version_and_path() -> None:
    payload = package_provenance()
    assert payload["version"]
    assert payload["packagePath"]
    assert payload["distribution"]["name"]
    assert payload["distribution"]["source"] in {
        "installed-package",
        "editable-install",
        "source-checkout",
        "unknown",
    }


def test_source_checkout_classification(tmp_path: Path) -> None:
    repo = tmp_path / "Hydracept"
    package = repo / "clients" / "python" / "hydracept"
    package.mkdir(parents=True)
    (repo / "architecture").mkdir()
    (repo / "architecture" / "pricing-catalog.yaml").write_text("service_fee_basis_points: 600\n")
    (repo / "clients" / "python" / "pyproject.toml").write_text("[project]\nname='hydracept'\n")
    (package / "__init__.py").write_text("")
    assert classify_distribution(package) == "source-checkout"
    assert points_at_repository(str(package), [repo])


def test_site_packages_not_repository(tmp_path: Path) -> None:
    site = tmp_path / "python" / "site-packages" / "hydracept"
    site.mkdir(parents=True)
    (site / "__init__.py").write_text("")
    assert classify_distribution(site) == "installed-package"
    assert not points_at_repository(str(site), [tmp_path / "Hydracept"])


def test_unrelated_src_path_is_not_editable(tmp_path: Path) -> None:
    package = tmp_path / "libs" / "src" / "hydracept"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    assert classify_distribution(package) in {"unknown", "installed-package"}
    assert classify_distribution(package) != "editable-install"
