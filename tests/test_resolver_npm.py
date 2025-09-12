"""Tests for NPM version resolver."""

import json
from typing import Optional
from unittest.mock import patch

import pytest

from src.versioning.cache import TTLCache
from src.versioning.models import Ecosystem, PackageRequest, ResolutionMode, VersionSpec
from src.versioning.resolvers.npm import NpmVersionResolver


@pytest.fixture
def cache():
    """Create a fresh cache for each test."""
    return TTLCache()


@pytest.fixture
def resolver(cache):
    """Create NPM resolver with cache."""
    return NpmVersionResolver(cache)


def create_request(identifier: str, spec_raw: Optional[str] = None, mode: Optional[ResolutionMode] = None) -> PackageRequest:
    """Helper to create package requests."""
    spec = None
    if spec_raw:
        spec = VersionSpec(raw=spec_raw, mode=mode or ResolutionMode.RANGE, include_prerelease=False)

    return PackageRequest(
        ecosystem=Ecosystem.NPM,
        identifier=identifier,
        requested_spec=spec,
        source="test",
        raw_token=f"{identifier}:{spec_raw}" if spec_raw else identifier
    )


class TestNpmVersionResolver:
    """Test NPM version resolver functionality."""

    @patch('src.versioning.resolvers.npm.get_json')
    def test_exact_version_present(self, mock_get_json, resolver):
        """Test exact version match when version exists."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.0.0": {},
                "1.1.0": {},
                "2.0.0": {}
            }
        })

        req = create_request("lodash", "1.1.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version == "1.1.0"
        assert count == 3
        assert error is None

    @patch('src.versioning.resolvers.npm.get_json')
    def test_exact_version_not_found(self, mock_get_json, resolver):
        """Test exact version when version doesn't exist."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.0.0": {},
                "1.1.0": {},
                "2.0.0": {}
            }
        })

        req = create_request("lodash", "1.2.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version is None
        assert count == 3
        assert "not found" in error

    @patch('src.versioning.resolvers.npm.get_json')
    def test_caret_range(self, mock_get_json, resolver):
        """Test caret range (^1.2.0) selects highest compatible version."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.2.0": {}, "1.2.1": {}, "1.3.0": {}, "1.4.0": {}, "2.0.0": {}
            }
        })

        req = create_request("lodash", "^1.2.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.2.0", "1.2.1", "1.3.0", "1.4.0", "2.0.0"])

        assert version == "1.4.0"  # Highest in ^1.2.0 range
        assert count == 5
        assert error is None

    @patch('src.versioning.resolvers.npm.get_json')
    def test_tilde_range(self, mock_get_json, resolver):
        """Test tilde range (~1.2.0) selects highest compatible patch version."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.2.0": {}, "1.2.1": {}, "1.2.9": {}, "1.3.0": {}
            }
        })

        req = create_request("lodash", "~1.2.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.2.0", "1.2.1", "1.2.9", "1.3.0"])

        assert version == "1.2.9"  # Highest in ~1.2.0 range
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.npm.get_json')
    def test_hyphen_range(self, mock_get_json, resolver):
        """Test hyphen range (1.2.3 - 1.4.5) selects highest in range."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.2.0": {}, "1.2.3": {}, "1.3.0": {}, "1.4.0": {}, "1.4.5": {}, "1.5.0": {}
            }
        })

        req = create_request("lodash", "1.2.3 - 1.4.5", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.2.0", "1.2.3", "1.3.0", "1.4.0", "1.4.5", "1.5.0"])

        assert version == "1.4.5"  # Highest in range
        assert count == 6
        assert error is None

    @patch('src.versioning.resolvers.npm.get_json')
    def test_x_range(self, mock_get_json, resolver):
        """Test x-range (1.2.x) selects highest matching version."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.1.9": {}, "1.2.0": {}, "1.2.1": {}, "1.2.9": {}, "1.3.0": {}
            }
        })

        req = create_request("lodash", "1.2.x", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.1.9", "1.2.0", "1.2.1", "1.2.9", "1.3.0"])

        assert version == "1.2.9"  # Highest 1.2.x version
        assert count == 5
        assert error is None

    @patch('src.versioning.resolvers.npm.get_json')
    def test_latest_mode(self, mock_get_json, resolver):
        """Test latest mode selects highest version."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.0.0": {}, "1.1.0": {}, "2.0.0": {}, "2.1.0": {}
            }
        })

        req = create_request("lodash")  # No spec = latest
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0", "2.1.0"])

        assert version == "2.1.0"  # Highest version
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.npm.get_json')
    def test_prerelease_excluded_by_default(self, mock_get_json, resolver):
        """Test that pre-releases are excluded by default."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "2.0.0-rc.1": {}, "2.0.0-rc.2": {}, "1.9.9": {}
            }
        })

        req = create_request("lodash", "^2.0.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["2.0.0-rc.1", "2.0.0-rc.2", "1.9.9"])

        assert version is None  # No stable version matches ^2.0.0
        assert count == 3
        assert "No versions match" in error

    @patch('src.versioning.resolvers.npm.get_json')
    def test_unsatisfiable_range(self, mock_get_json, resolver):
        """Test unsatisfiable range returns error."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.0.0": {}, "1.1.0": {}, "2.0.0": {}
            }
        })

        req = create_request("lodash", "^3.0.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version is None
        assert count == 3
        assert "No versions match" in error

    @patch('src.versioning.resolvers.npm.get_json')
    def test_fetch_candidates_caching(self, mock_get_json, resolver, cache):
        """Test that fetch_candidates uses caching."""
        mock_response = {
            "versions": {
                "1.0.0": {},
                "1.1.0": {},
                "2.0.0": {}
            }
        }
        mock_get_json.return_value = (200, {}, mock_response)

        req = create_request("lodash")

        # First call should hit network
        candidates1 = resolver.fetch_candidates(req)
        assert mock_get_json.call_count == 1
        assert candidates1 == ["1.0.0", "1.1.0", "2.0.0"]

        # Second call should use cache
        candidates2 = resolver.fetch_candidates(req)
        assert mock_get_json.call_count == 1  # Still 1, used cache
        assert candidates2 == candidates1

    @patch('src.versioning.resolvers.npm.get_json')
    def test_fetch_candidates_network_error(self, mock_get_json, resolver):
        """Test fetch_candidates handles network errors gracefully."""
        mock_get_json.return_value = (404, {}, None)

        req = create_request("nonexistent-package")
        candidates = resolver.fetch_candidates(req)

    @patch('src.versioning.resolvers.npm.get_json')
    def test_latest_mode_excludes_prereleases(self, mock_get_json, resolver):
        """Test latest mode excludes prerelease versions and selects highest stable."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "1.0.0": {},
                "2.0.0-rc.1": {},
                "1.9.9": {},
                "2.0.0-beta.2": {}
            }
        })

        req = create_request("lodash")  # No spec = latest
        version, count, error = resolver.pick(req, ["1.0.0", "2.0.0-rc.1", "1.9.9", "2.0.0-beta.2"])

        assert version == "1.9.9"  # Highest stable version
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.npm.get_json')
    def test_latest_mode_only_prereleases(self, mock_get_json, resolver):
        """Test latest mode when only prerelease versions are available."""
        mock_get_json.return_value = (200, {}, {
            "versions": {
                "2.0.0-rc.1": {},
                "2.0.0-beta.2": {},
                "3.0.0-alpha.1": {}
            }
        })

        req = create_request("lodash")  # No spec = latest
        version, count, error = resolver.pick(req, ["2.0.0-rc.1", "2.0.0-beta.2", "3.0.0-alpha.1"])

        assert version is None
        assert count == 3
        assert error == "No stable versions available"


@patch('src.versioning.resolvers.npm.get_json')
def test_fetch_candidates_encodes_scoped_name(mock_get_json, resolver):
    """Ensure scoped npm names are percent-encoded as a single path segment."""
    mock_get_json.return_value = (200, {}, {"versions": {}})

    req = create_request("@types/node")
    _ = resolver.fetch_candidates(req)

    called_url = mock_get_json.call_args[0][0]
    assert "%40types%2Fnode" in called_url
    assert "@types/node" not in called_url
