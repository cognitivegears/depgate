import json
import types
from typing import Any, Dict, Optional

import pytest

from registry.depsdev.enrich import enrich_metapackage


class DummyMP:
    def __init__(self, name: str = "left-pad"):
        self.pkg_name: str = name
        self.license_id: Optional[str] = None
        self.license_source: Optional[str] = None
        self.license_available: Optional[bool] = None
        self.repo_url_normalized: Optional[str] = None
        self.repo_host: Optional[str] = None
        self.provenance: Dict[str, Any] = {}
        self.resolved_version: Optional[str] = None


class FakeClient:
    def __init__(self, project_json=None, version_json=None, status=200):
        self.base_url = "https://api.deps.dev/v3"
        self._eco = "npm"
        self._name = "left-pad"
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
        return self.status, {}, dict(self.project_json)

    def get_version(self, ecosystem, name, version):
        return self.status, {}, dict(self.version_json)


def test_backfill_license_when_missing(monkeypatch):
    # Arrange: deps.dev returns license at version-level
    mp = DummyMP()
    client = FakeClient(
        project_json={},
        version_json={"licenses": [{"id": "MIT"}]},
        status=200,
    )

    # Disable repo normalization side-effects (not needed for this test)
    monkeypatch.setattr("registry.depsdev.enrich.normalize_repo_url", lambda url: types.SimpleNamespace(normalized_url=url, host="github"))

    # Act
    enrich_metapackage(mp, "npm", "left-pad", "1.0.0", client=client)  # type: ignore[arg-type]

    # Assert: backfilled license fields
    assert mp.license_id == "MIT"
    assert mp.license_available is True
    assert mp.license_source == "deps.dev"
    assert isinstance(mp.provenance, dict)
    assert "depsdev" in mp.provenance
    assert "fields" in mp.provenance["depsdev"]
    assert mp.provenance["depsdev"]["fields"]["license"]["value"] == "MIT"


def test_discrepancy_recorded_when_license_differs(monkeypatch):
    # Arrange: package already has a different license; deps.dev returns alternate
    mp = DummyMP()
    mp.license_id = "Apache-2.0"  # existing
    client = FakeClient(
        project_json={},
        version_json={"licenses": [{"id": "MIT"}]},
        status=200,
    )

    monkeypatch.setattr("registry.depsdev.enrich.normalize_repo_url", lambda url: types.SimpleNamespace(normalized_url=url, host="github"))

    # Act
    enrich_metapackage(mp, "npm", "left-pad", "1.0.0", client=client)  # type: ignore[arg-type]

    # Assert: existing license preserved, discrepancy recorded in provenance
    assert mp.license_id == "Apache-2.0"
    dd = mp.provenance.get("depsdev", {})
    discrepancies = dd.get("discrepancies", [])
    # One of the discrepancies should mention license_id with deps.dev value "MIT"
    assert any(d.get("field") == "license_id" and d.get("depsdev") == "MIT" for d in discrepancies)


def test_repo_alt_and_normalization_backfilled(monkeypatch):
    # Arrange: deps.dev provides a repository URL alternative; package has none
    mp = DummyMP()
    client = FakeClient(
        project_json={"links": {"repository": "https://github.com/owner/repo"}},
        version_json={},
        status=200,
    )

    # Provide a deterministic normalizer
    def fake_normalize(url):
        return types.SimpleNamespace(normalized_url=url.rstrip("/"), host="github")

    monkeypatch.setattr("registry.depsdev.enrich.normalize_repo_url", fake_normalize)

    # Act
    enrich_metapackage(mp, "npm", mp.pkg_name, "1.0.0", client=client)  # type: ignore[arg-type]

    # Assert: repo_url_normalized populated and provenance gets repo_url_alt
    assert mp.repo_url_normalized == "https://github.com/owner/repo"
    assert mp.repo_host == "github"
    dd = mp.provenance.get("depsdev", {})
    assert dd.get("fields", {}).get("repo_url_alt") == "https://github.com/owner/repo"
