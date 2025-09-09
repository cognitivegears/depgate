"""Tests for PyPI version resolver."""

import json
from typing import Optional
from unittest.mock import patch

import pytest

from src.versioning.cache import TTLCache
from src.versioning.models import Ecosystem, PackageRequest, ResolutionMode, VersionSpec
from src.versioning.resolvers.pypi import PyPIVersionResolver


@pytest.fixture
def cache():
    """Create a fresh cache for each test."""
    return TTLCache()


@pytest.fixture
def resolver(cache):
    """Create PyPI resolver with cache."""
    return PyPIVersionResolver(cache)


def create_request(identifier: str, spec_raw: Optional[str] = None, mode: Optional[ResolutionMode] = None) -> PackageRequest:
    """Helper to create package requests."""
    spec = None
    if spec_raw:
        spec = VersionSpec(raw=spec_raw, mode=mode or ResolutionMode.RANGE, include_prerelease=False)

    return PackageRequest(
        ecosystem=Ecosystem.PYPI,
        identifier=identifier,
        requested_spec=spec,
        source="test",
        raw_token=f"{identifier}:{spec_raw}" if spec_raw else identifier
    )


class TestPyPIVersionResolver:
    """Test PyPI version resolver functionality."""

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_exact_version_present(self, mock_get_json, resolver):
        """Test exact version match when version exists."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz"}],
                "1.1.0": [{"filename": "pkg-1.1.0.tar.gz"}],
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz"}]
            }
        })

        req = create_request("requests", "1.1.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version == "1.1.0"
        assert count == 3
        assert error is None

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_exact_version_not_found(self, mock_get_json, resolver):
        """Test exact version when version doesn't exist."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz"}],
                "1.1.0": [{"filename": "pkg-1.1.0.tar.gz"}],
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz"}]
            }
        })

        req = create_request("requests", "1.2.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version is None
        assert count == 3
        assert "not found" in error

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_range_specifier(self, mock_get_json, resolver):
        """Test PEP 440 range specifier (>=1.0,<2.0) selects highest compatible version."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz"}],
                "1.1.0": [{"filename": "pkg-1.1.0.tar.gz"}],
                "1.5.0": [{"filename": "pkg-1.5.0.tar.gz"}],
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz"}]
            }
        })

        req = create_request("requests", ">=1.0,<2.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "1.5.0", "2.0.0"])

        assert version == "1.5.0"  # Highest in range
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_latest_mode(self, mock_get_json, resolver):
        """Test latest mode selects highest version."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz"}],
                "1.1.0": [{"filename": "pkg-1.1.0.tar.gz"}],
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz"}],
                "2.1.0": [{"filename": "pkg-2.1.0.tar.gz"}]
            }
        })

        req = create_request("requests")  # No spec = latest
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0", "2.1.0"])

        assert version == "2.1.0"  # Highest version
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_yanked_versions_excluded(self, mock_get_json, resolver):
        """Test that yanked versions are excluded from candidates."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz", "yanked": False}],
                "1.1.0": [{"filename": "pkg-1.1.0.tar.gz", "yanked": True}],  # Yanked
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz", "yanked": False}]
            }
        })

        req = create_request("requests")
        candidates = resolver.fetch_candidates(req)

        # Should exclude 1.1.0 (yanked)
        assert "1.0.0" in candidates
        assert "1.1.0" not in candidates
        assert "2.0.0" in candidates

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_prerelease_excluded_by_default(self, mock_get_json, resolver):
        """Test that pre-releases are excluded by default."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "2.0.0rc1": [{"filename": "pkg-2.0.0rc1.tar.gz"}],
                "2.0.0rc2": [{"filename": "pkg-2.0.0rc2.tar.gz"}],
                "1.9.9": [{"filename": "pkg-1.9.9.tar.gz"}]
            }
        })

        req = create_request("requests", ">=2.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["2.0.0rc1", "2.0.0rc2", "1.9.9"])

        assert version is None  # No stable version matches >=2.0
        assert count == 3
        assert "No versions match" in error

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_no_prerelease_fallback_when_no_stable(self, mock_get_json, resolver):
        """Test that pre-releases are not selected when no stable versions satisfy the spec (strict)."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "2.0.0rc1": [{"filename": "pkg-2.0.0rc1.tar.gz"}],
                "2.0.0rc2": [{"filename": "pkg-2.0.0rc2.tar.gz"}],
                "1.9.9": [{"filename": "pkg-1.9.9.tar.gz"}]
            }
        })

        req = create_request("requests", ">=2.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["2.0.0rc1", "2.0.0rc2", "1.9.9"])

        assert version is None  # Strict: no fallback to prerelease
        assert count == 3
        assert "No versions match" in error

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_unsatisfiable_range(self, mock_get_json, resolver):
        """Test unsatisfiable range returns error."""
        mock_get_json.return_value = (200, {}, {
            "releases": {
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz"}],
                "1.1.0": [{"filename": "pkg-1.1.0.tar.gz"}],
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz"}]
            }
        })

        req = create_request("requests", ">=3.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version is None
        assert count == 3
        assert "No versions match" in error

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_fetch_candidates_caching(self, mock_get_json, resolver, cache):
        """Test that fetch_candidates uses caching."""
        mock_response = {
            "releases": {
                "1.0.0": [{"filename": "pkg-1.0.0.tar.gz"}],
                "1.1.0": [{"filename": "pkg-1.1.0.tar.gz"}],
                "2.0.0": [{"filename": "pkg-2.0.0.tar.gz"}]
            }
        }
        mock_get_json.return_value = (200, {}, mock_response)

        req = create_request("requests")

        # First call should hit network
        candidates1 = resolver.fetch_candidates(req)
        assert mock_get_json.call_count == 1
        assert candidates1 == ["1.0.0", "1.1.0", "2.0.0"]

        # Second call should use cache
        candidates2 = resolver.fetch_candidates(req)
        assert mock_get_json.call_count == 1  # Still 1, used cache
        assert candidates2 == candidates1

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_fetch_candidates_network_error(self, mock_get_json, resolver):
        """Test fetch_candidates handles network errors gracefully."""
        mock_get_json.return_value = (404, {}, None)

        req = create_request("nonexistent-package")
        candidates = resolver.fetch_candidates(req)

        assert candidates == []

    @patch('src.versioning.resolvers.pypi.get_json')
    def test_empty_releases_handled(self, mock_get_json, resolver):
        """Test handling of packages with no releases."""
        mock_get_json.return_value = (200, {}, {"releases": {}})

        req = create_request("empty-package")
        candidates = resolver.fetch_candidates(req)

        assert candidates == []
