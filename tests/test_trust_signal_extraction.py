"""Tests for ecosystem-specific trust signal extraction functions."""

from registry.npm.enrich import (
    _extract_registry_signature,
    _extract_provenance,
    _ordered_versions,
    _set_npm_trust_signals,
)
from registry.pypi.client import (
    _extract_simple_trust,
    _extract_legacy_json_signature,
    _release_timestamp_ms,
    _ordered_release_versions,
)
from registry.maven.discovery import (
    _has_any_artifact_suffix,
    _collect_trust_signals,
    _fetch_metadata_root,
)
from metapackage import MetaPackage


# ──────────────────────────── npm ────────────────────────────


class TestNpmExtractRegistrySignature:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_with_dist_signatures(self):
        info = {"dist": {"signatures": [{"keyid": "abc", "sig": "xyz"}]}}
        assert _extract_registry_signature(info) is True

    def test_with_npm_signature_string(self):
        info = {"dist": {"npm-signature": "some-sig-value"}}
        assert _extract_registry_signature(info) is True

    def test_no_signature(self):
        info = {"dist": {"shasum": "abc"}}
        assert _extract_registry_signature(info) is False

    def test_empty_signatures_list(self):
        info = {"dist": {"signatures": []}}
        assert _extract_registry_signature(info) is False

    def test_blank_npm_signature(self):
        info = {"dist": {"npm-signature": "   "}}
        assert _extract_registry_signature(info) is False

    def test_none_input(self):
        assert _extract_registry_signature(None) is None

    def test_missing_dist(self):
        assert _extract_registry_signature({}) is False

    def test_dist_not_dict(self):
        info = {"dist": "not-a-dict"}
        assert _extract_registry_signature(info) is None


class TestNpmExtractProvenance:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_dist_attestations_dict_with_url(self):
        info = {"dist": {"attestations": {"url": "https://example.com/att"}}}
        present, url, source = _extract_provenance(info)
        assert present is True
        assert url == "https://example.com/att"
        assert source == "dist.attestations"

    def test_version_attestations_list(self):
        info = {"attestations": [{"url": "https://att.example.com"}]}
        present, url, source = _extract_provenance(info)
        assert present is True
        assert url == "https://att.example.com"
        assert source == "version.attestations"

    def test_dist_provenance_string(self):
        info = {"dist": {"provenance": "https://prov.example.com"}}
        present, url, source = _extract_provenance(info)
        assert present is True
        assert url == "https://prov.example.com"
        assert source == "dist.provenance"

    def test_version_provenance_dict_no_url(self):
        info = {"provenance": {"bundleUrl": "something"}}
        present, url, source = _extract_provenance(info)
        assert present is True
        assert url is None
        assert source == "version.provenance"

    def test_no_provenance(self):
        info = {"dist": {"shasum": "abc"}}
        present, url, source = _extract_provenance(info)
        assert present is False
        assert url is None
        assert source is None

    def test_none_input(self):
        present, url, source = _extract_provenance(None)
        assert present is None
        assert url is None

    def test_empty_string_ignored(self):
        info = {"dist": {"provenance": "   "}}
        # Empty string should be skipped, so falls through to next candidate
        present, url, source = _extract_provenance(info)
        # No non-empty candidates -> False
        assert present is False


class TestNpmOrderedVersions:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_orders_by_time(self):
        packument = {
            "time": {
                "created": "2020-01-01T00:00:00Z",
                "modified": "2024-01-01T00:00:00Z",
                "1.0.0": "2021-01-01T00:00:00Z",
                "2.0.0": "2020-06-01T00:00:00Z",
                "3.0.0": "2022-01-01T00:00:00Z",
            },
            "versions": {"1.0.0": {}, "2.0.0": {}, "3.0.0": {}},
        }
        result = _ordered_versions(packument)
        assert result == ["2.0.0", "1.0.0", "3.0.0"]

    def test_falls_back_to_semver(self):
        packument = {
            "time": {},
            "versions": {"2.0.0": {}, "1.0.0": {}, "3.0.0": {}},
        }
        result = _ordered_versions(packument)
        assert result == ["1.0.0", "2.0.0", "3.0.0"]

    def test_empty_packument(self):
        result = _ordered_versions({})
        assert result == []


class TestNpmSetTrustSignals:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_sets_signals_and_regression(self):
        packument = {
            "time": {
                "1.0.0": "2023-01-01T00:00:00Z",
                "2.0.0": "2024-01-01T00:00:00Z",
            },
            "versions": {
                "1.0.0": {"dist": {"signatures": [{"keyid": "k", "sig": "s"}]}},
                "2.0.0": {"dist": {}},
            },
        }
        pkg = MetaPackage("test", "npm")
        _set_npm_trust_signals(pkg, packument, "2.0.0")

        assert pkg.registry_signature_present is False
        assert pkg.previous_registry_signature_present is True
        assert pkg.registry_signature_regressed is True
        assert pkg.previous_release_version == "1.0.0"
        assert pkg.trust_score is not None

    def test_first_version_no_previous(self):
        packument = {
            "time": {"1.0.0": "2023-01-01T00:00:00Z"},
            "versions": {
                "1.0.0": {"dist": {"signatures": [{"keyid": "k", "sig": "s"}]}},
            },
        }
        pkg = MetaPackage("test", "npm")
        _set_npm_trust_signals(pkg, packument, "1.0.0")

        assert pkg.previous_release_version is None
        assert pkg.previous_registry_signature_present is None
        assert pkg.registry_signature_regressed is None


# ──────────────────────────── PyPI ────────────────────────────


class TestPypiExtractSimpleTrust:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_gpg_sig_present(self):
        simple = {
            "files": [
                {"version": "1.0.0", "gpg-sig": True, "filename": "pkg-1.0.0.tar.gz"},
            ]
        }
        sig, prov, prov_url = _extract_simple_trust(simple, "1.0.0")
        assert sig is True
        assert prov is False

    def test_provenance_present(self):
        simple = {
            "files": [
                {
                    "version": "1.0.0",
                    "provenance": "https://provenance.example.com",
                    "filename": "pkg-1.0.0.tar.gz",
                },
            ]
        }
        sig, prov, prov_url = _extract_simple_trust(simple, "1.0.0")
        assert prov is True
        assert prov_url == "https://provenance.example.com"

    def test_version_not_found(self):
        simple = {
            "files": [
                {"version": "2.0.0", "gpg-sig": True, "filename": "pkg-2.0.0.tar.gz"},
            ]
        }
        sig, prov, prov_url = _extract_simple_trust(simple, "1.0.0")
        assert sig is None
        assert prov is None

    def test_none_input(self):
        sig, prov, prov_url = _extract_simple_trust(None, "1.0.0")
        assert sig is None

    def test_no_signals(self):
        simple = {
            "files": [
                {"version": "1.0.0", "filename": "pkg-1.0.0.tar.gz"},
            ]
        }
        sig, prov, prov_url = _extract_simple_trust(simple, "1.0.0")
        assert sig is False
        assert prov is False


class TestPypiLegacyJsonSignature:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_has_sig_true(self):
        releases = {
            "1.0.0": [{"has_sig": True, "filename": "pkg-1.0.0.tar.gz"}],
        }
        assert _extract_legacy_json_signature(releases, "1.0.0") is True

    def test_has_sig_false(self):
        releases = {
            "1.0.0": [{"has_sig": False, "filename": "pkg-1.0.0.tar.gz"}],
        }
        assert _extract_legacy_json_signature(releases, "1.0.0") is False

    def test_version_missing(self):
        releases = {"2.0.0": [{"has_sig": True}]}
        assert _extract_legacy_json_signature(releases, "1.0.0") is None

    def test_empty_files(self):
        releases = {"1.0.0": []}
        assert _extract_legacy_json_signature(releases, "1.0.0") is None


class TestPypiReleaseTimestamp:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_parses_iso8601(self):
        files = [{"upload_time_iso_8601": "2024-06-15T12:00:00Z"}]
        ms = _release_timestamp_ms(files)
        assert ms is not None
        assert ms > 0

    def test_empty_list(self):
        assert _release_timestamp_ms([]) is None

    def test_picks_latest(self):
        files = [
            {"upload_time_iso_8601": "2024-01-01T00:00:00Z"},
            {"upload_time_iso_8601": "2024-06-01T00:00:00Z"},
        ]
        ms = _release_timestamp_ms(files)
        # Should pick the later timestamp
        single = _release_timestamp_ms([files[1]])
        assert ms == single


class TestPypiOrderedReleaseVersions:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_orders_by_upload_time(self):
        releases = {
            "1.0.0": [{"upload_time_iso_8601": "2024-06-01T00:00:00Z"}],
            "0.9.0": [{"upload_time_iso_8601": "2024-01-01T00:00:00Z"}],
            "1.1.0": [{"upload_time_iso_8601": "2024-09-01T00:00:00Z"}],
        }
        result = _ordered_release_versions(releases)
        assert result == ["0.9.0", "1.0.0", "1.1.0"]

    def test_fallback_to_dict_order(self):
        releases = {
            "1.0.0": "not-a-list",
            "2.0.0": "not-a-list",
        }
        result = _ordered_release_versions(releases)
        assert set(result) == {"1.0.0", "2.0.0"}


# ──────────────────────────── Maven ────────────────────────────


class TestMavenArtifactExists:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_returns_false_on_exception(self, monkeypatch):
        """_artifact_exists returns False when the HTTP call fails."""
        import registry.maven.discovery as disc

        def _fake_head(url, *, context, **kwargs):
            raise ConnectionError("test")

        monkeypatch.setattr(disc, "safe_head", _fake_head)
        assert disc._artifact_exists("https://example.com/fake.pom.asc") is False

    def test_passes_fatal_false_to_safe_head(self, monkeypatch):
        """_artifact_exists passes fatal=False so SystemExit is not raised."""
        import registry.maven.discovery as disc

        captured = {}

        class FakeResp:
            status_code = 200

        def _spy_head(url, *, context, fatal=True, **kwargs):
            captured["fatal"] = fatal
            return FakeResp()

        monkeypatch.setattr(disc, "safe_head", _spy_head)
        disc._artifact_exists("https://example.com/fake.pom")
        assert captured["fatal"] is False


class TestMavenFetchMetadataRoot:
    def setup_method(self):
        MetaPackage.instances.clear()
        import registry.maven.discovery as disc
        disc._metadata_cache.clear()

    def test_returns_none_on_network_error(self, monkeypatch):
        """_fetch_metadata_root returns None instead of crashing on network errors."""
        import registry.maven.discovery as disc
        import requests

        def _fake_get(url, *, context, fatal=True, **kwargs):
            raise requests.ConnectionError("test")

        monkeypatch.setattr(disc, "safe_get", _fake_get)
        assert _fetch_metadata_root("com.example", "lib") is None

    def test_cache_uses_lock(self):
        """_metadata_cache_lock exists and is a threading.Lock."""
        import threading
        import registry.maven.discovery as disc
        assert isinstance(disc._metadata_cache_lock, type(threading.Lock()))


class TestMavenHasAnyArtifactSuffix:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_returns_none_for_empty_version(self):
        assert _has_any_artifact_suffix("g", "a", "", [".pom.asc"]) is None

    def test_short_circuits_on_first_hit(self, monkeypatch):
        """Should return True as soon as the first suffix matches."""
        import registry.maven.discovery as disc

        call_count = 0

        def _counting_exists(url):
            nonlocal call_count
            call_count += 1
            return True  # Every check succeeds

        monkeypatch.setattr(disc, "_artifact_exists", _counting_exists)
        result = _has_any_artifact_suffix("g", "a", "1.0", [".pom.asc", ".jar.asc", ".pom.sha1"])
        assert result is True
        assert call_count == 1  # Short-circuited after first hit

    def test_returns_false_when_none_match(self, monkeypatch):
        import registry.maven.discovery as disc

        monkeypatch.setattr(disc, "_artifact_exists", lambda url: False)
        result = _has_any_artifact_suffix("g", "a", "1.0", [".pom.asc", ".jar.asc"])
        assert result is False


class TestMavenCollectTrustSignals:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_collects_all_signal_types(self, monkeypatch):
        import registry.maven.discovery as disc

        def _fake_exists(url):
            return ".asc" in url or ".sha256" in url

        monkeypatch.setattr(disc, "_artifact_exists", _fake_exists)
        signals = _collect_trust_signals("com.example", "lib", "1.0.0")
        assert signals["registry_signature_present"] is True
        assert signals["provenance_present"] is False  # no .sigstore match
        assert signals["checksums_present"] is True

    def test_returns_none_for_empty_version(self, monkeypatch):
        import registry.maven.discovery as disc

        monkeypatch.setattr(disc, "_artifact_exists", lambda url: True)
        signals = _collect_trust_signals("com.example", "lib", "")
        # All signals should be None for empty version
        assert signals["registry_signature_present"] is None
        assert signals["provenance_present"] is None
        assert signals["checksums_present"] is None
