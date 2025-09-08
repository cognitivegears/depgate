import json
from unittest.mock import MagicMock

import pytest

from metapackage import MetaPackage


class DummyResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def _make_repo_ref(normalized_url, host, owner, repo, directory=None):
    # Minimal object with attributes used by registry modules
    class _Ref:
        def __init__(self):
            self.normalized_url = normalized_url
            self.host = host
            self.owner = owner
            self.repo = repo
            self.directory = directory
    return _Ref()


def test_e2e_pypi_rtd_resolution(monkeypatch):
    # Arrange: fake Warehouse JSON with RTD documentation link
    pkg_name = "rtdpkg"
    mp = MetaPackage(pkg_name)

    pypi_json = {
        "info": {
            "version": "1.0.0",
            "project_urls": {"Documentation": f"https://{pkg_name}.readthedocs.io/"},
            "home_page": "https://example.com"
        },
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00.000Z"}]
        }
    }

    # Patch registry.pypi safe_get to return our JSON
    import registry.pypi as pypi_mod
    def fake_safe_get(url, context=None, params=None, headers=None):
        return DummyResponse(200, json.dumps(pypi_json))
    monkeypatch.setattr(pypi_mod, "safe_get", fake_safe_get)

    # Resolve RTD -> repo and normalize
    monkeypatch.setattr(pypi_mod, "_maybe_resolve_via_rtd", lambda u: "https://github.com/owner/repo")
    monkeypatch.setattr(pypi_mod, "normalize_repo_url",
                        lambda url: _make_repo_ref("https://github.com/owner/repo", "github", "owner", "repo"))

    # Stub GitHub client and version matcher
    class GHClientStub:
        def get_repo(self, owner, repo):
            return {"stargazers_count": 123, "pushed_at": "2023-02-01T00:00:00Z"}
        def get_contributors_count(self, owner, repo):
            return 10
        def get_releases(self, owner, repo):
            return [{"name": "v1.0.0", "tag_name": "v1.0.0"}]
    monkeypatch.setattr(pypi_mod, "GitHubClient", lambda: GHClientStub())

    vm = MagicMock()
    vm.find_match.return_value = {"matched": True, "match_type": "exact", "artifact": {"name": "v1.0.0"}, "tag_or_release": "v1.0.0"}
    monkeypatch.setattr(pypi_mod, "VersionMatcher", lambda: vm)

    # Act
    pypi_mod.recv_pkg_info([mp])

    # Assert
    assert mp.repo_url_normalized == "https://github.com/owner/repo"
    assert mp.repo_resolved is True
    assert mp.repo_exists is True
    assert mp.repo_version_match and mp.repo_version_match.get("matched") is True
    # rtd slug should be inferred from docs host
    assert mp.provenance and mp.provenance.get("rtd_slug") == pkg_name


def test_e2e_npm_monorepo_repository_object(monkeypatch):
    # Arrange: packument with repository object including monorepo directory
    pkg_name = "babel-core"
    mp = MetaPackage(pkg_name)

    packument = {
        "dist-tags": {"latest": "7.0.0"},
        "versions": {
            "7.0.0": {
                "repository": {
                    "type": "git",
                    "url": "git+https://github.com/babel/babel.git",
                    "directory": "packages/babel-core"
                },
                "bugs": "https://github.com/babel/babel/issues"
            }
        }
    }

    import registry.npm as npm_mod

    def fake_safe_get(url, context=None, params=None, headers=None):
        # get_package_details concatenates url + pkg_name; ignore and return packument
        return DummyResponse(200, json.dumps(packument))
    monkeypatch.setattr(npm_mod, "safe_get", fake_safe_get)

    # Normalize repo URL; preserve directory hint in object (not used for API)
    monkeypatch.setattr(npm_mod, "normalize_repo_url",
                        lambda u, d=None: _make_repo_ref("https://github.com/babel/babel", "github", "babel", "babel", d))

    class GHClientStub:
        def get_repo(self, owner, repo):
            return {"stargazers_count": 60000, "pushed_at": "2023-04-01T00:00:00Z"}
        def get_contributors_count(self, owner, repo):
            return 400
        def get_releases(self, owner, repo):
            return [{"name": "7.0.0", "tag_name": "7.0.0"}]
    monkeypatch.setattr(npm_mod, "GitHubClient", lambda: GHClientStub())
    vm = MagicMock()
    vm.find_match.return_value = {"matched": True, "match_type": "exact", "artifact": {"name": "7.0.0"}, "tag_or_release": "7.0.0"}
    monkeypatch.setattr(npm_mod, "VersionMatcher", lambda: vm)

    # Act
    npm_mod.get_package_details(mp, url="https://registry.npmjs.org/")

    # Assert
    assert mp.repo_url_normalized == "https://github.com/babel/babel"
    assert mp.repo_resolved is True
    assert mp.repo_exists is True
    assert mp.repo_version_match and mp.repo_version_match.get("matched") is True
    # Provenance should capture repository field + directory
    assert mp.provenance is not None
    assert mp.provenance.get("npm_repository_field") == "git+https://github.com/babel/babel.git"
    assert mp.provenance.get("npm_repository_directory") == "packages/babel-core"


def test_e2e_maven_parent_scm(monkeypatch):
    # Arrange: traversal returns wrapper with scm + provenance
    coords = ("org.apache.commons", "commons-lang3")
    mp = MetaPackage(f"{coords[0]}:{coords[1]}")

    import registry.maven as maven_mod

    monkeypatch.setattr(maven_mod, "_resolve_latest_version", lambda g, a: "1.2.3")
    def fake_traverse_for_scm(group, artifact, version, provenance, depth=0, max_depth=8):
        return {
            "scm": {"url": "https://github.com/example/project"},
            "provenance": {"maven_pom.scm.url": "https://github.com/example/project"}
        }
    monkeypatch.setattr(maven_mod, "_traverse_for_scm", fake_traverse_for_scm)

    # Normalize to canonical URL
    monkeypatch.setattr(maven_mod, "normalize_repo_url",
                        lambda u: _make_repo_ref("https://github.com/example/project", "github", "example", "project"))

    class GHClientStub:
        def get_repo(self, owner, repo):
            return {"stargazers_count": 123, "pushed_at": "2023-01-01T00:00:00Z"}
        def get_contributors_count(self, owner, repo):
            return 10
        def get_releases(self, owner, repo):
            return [{"name": "1.2.3", "tag_name": "1.2.3"}]
    monkeypatch.setattr(maven_mod, "GitHubClient", lambda: GHClientStub())
    vm = MagicMock()
    vm.find_match.return_value = {"matched": True, "match_type": "exact", "artifact": {"name": "1.2.3"}, "tag_or_release": "1.2.3"}
    monkeypatch.setattr(maven_mod, "VersionMatcher", lambda: vm)

    # Act
    maven_mod._enrich_with_repo(mp, coords[0], coords[1], None)

    # Assert
    assert mp.repo_url_normalized == "https://github.com/example/project"
    assert mp.repo_resolved is True
    assert mp.repo_exists is True
    assert mp.repo_version_match and mp.repo_version_match.get("matched") is True
    assert mp.provenance and mp.provenance.get("maven_pom.scm.url") == "https://github.com/example/project"
