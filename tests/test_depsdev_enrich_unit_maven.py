import types
from typing import Any, Dict, Optional

import pytest

from registry.depsdev.enrich import enrich_metapackage


class DummyMP:
    def __init__(self, name: str = "junit-jupiter-api", org: str = "org.junit.jupiter", resolved_version: Optional[str] = "5.11.0"):
        self.pkg_name: str = name
        self.org_id: str = org
        self.license_id: Optional[str] = None
        self.license_source: Optional[str] = None
        self.license_available: Optional[bool] = None
        self.repo_url_normalized: Optional[str] = None
        self.repo_host: Optional[str] = None
        self.provenance: Dict[str, Any] = {}
        self.resolved_version: Optional[str] = resolved_version


class FakeClient:
    def __init__(self, project_json=None, version_json=None, status=200):
        self.base_url = "https://api.deps.dev/v3"
        self.project_json = project_json if project_json is not None else {}
        self.version_json = version_json if version_json is not None else {}
        self.status = status

    def _eco_value(self, eco):
        return eco

    def normalize_name(self, eco, name):
        return name

    def normalize_version(self, eco, version):
        return version

    def get_project(self, ecosystem, name):
        # Simulate deps.dev Maven project doc (declaredLicenses)
        return self.status, {}, dict(self.project_json)

    def get_version(self, ecosystem, name, version):
        # Simulate deps.dev Maven version doc (licenses with expression)
        return self.status, {}, dict(self.version_json)


def test_maven_backfill_license_from_declared_licenses(monkeypatch):
    """When version-level is missing but project includes declaredLicenses, backfill license."""
    mp = DummyMP()
    client = FakeClient(
        project_json={"declaredLicenses": ["EPL-2.0"]},
        version_json={},  # no version licenses in this case
        status=200,
    )

    # Disable repo normalization side-effects
    monkeypatch.setattr("registry.depsdev.enrich.normalize_repo_url", lambda url: types.SimpleNamespace(normalized_url=url, host="github"))

    # Act
    enrich_metapackage(mp, "maven", f"{mp.org_id}:{mp.pkg_name}", mp.resolved_version, client=client)  # type: ignore[arg-type]

    # Assert
    assert mp.license_id == "EPL-2.0"
    assert mp.license_available is True
    assert mp.license_source == "deps.dev"
    assert "depsdev" in mp.provenance
    assert mp.provenance["depsdev"]["fields"]["license"]["value"] == "EPL-2.0"


def test_maven_backfill_license_from_expression(monkeypatch):
    """When deps.dev returns only an SPDX expression, use it for id and expression."""
    mp = DummyMP()
    client = FakeClient(
        project_json={},  # nothing at project level
        version_json={"licenses": [{"expression": "EPL-2.0"}]},
        status=200,
    )

    monkeypatch.setattr("registry.depsdev.enrich.normalize_repo_url", lambda url: types.SimpleNamespace(normalized_url=url, host="github"))

    enrich_metapackage(mp, "maven", f"{mp.org_id}:{mp.pkg_name}", mp.resolved_version, client=client)  # type: ignore[arg-type]

    assert mp.license_id == "EPL-2.0"
    assert mp.license_available is True
    assert mp.license_source == "deps.dev"
    dd = mp.provenance.get("depsdev", {})
    lic = dd.get("fields", {}).get("license", {})
    assert lic.get("value") == "EPL-2.0"
    assert lic.get("expression") == "EPL-2.0"
