"""Tests for NuGet version resolver."""

import json
from typing import Optional
from unittest.mock import patch

import pytest

from src.versioning.cache import TTLCache
from src.versioning.models import Ecosystem, PackageRequest, ResolutionMode, VersionSpec
from src.versioning.resolvers.nuget import NuGetVersionResolver


@pytest.fixture
def cache():
    """Create a fresh cache for each test."""
    return TTLCache()


@pytest.fixture
def resolver(cache):
    """Create NuGet resolver with cache."""
    return NuGetVersionResolver(cache)


def create_request(identifier: str, spec_raw: Optional[str] = None, mode: Optional[ResolutionMode] = None) -> PackageRequest:
    """Helper to create package requests."""
    spec = None
    if spec_raw:
        spec = VersionSpec(raw=spec_raw, mode=mode or ResolutionMode.RANGE, include_prerelease=False)

    return PackageRequest(
        ecosystem=Ecosystem.NUGET,
        identifier=identifier,
        requested_spec=spec,
        source="test",
        raw_token=f"{identifier}:{spec_raw}" if spec_raw else identifier
    )


class TestNuGetVersionResolver:
    """Test NuGet version resolver functionality."""

    @patch('src.versioning.resolvers.nuget.get_json')
    def test_v3_exact_version_present(self, mock_get_json, resolver):
        """Test exact version match when version exists via V3 API."""
        # Mock service index
        mock_get_json.side_effect = [
            (200, {}, {
                "version": "3.0.0",
                "resources": [
                    {
                        "@id": "https://api.nuget.org/v3/registration5-gz-semver2/",
                        "@type": "RegistrationsBaseUrl/3.6.0"
                    }
                ]
            }),
            (200, {}, {
                "items": [
                    {
                        "items": [
                            {
                                "catalogEntry": {
                                    "version": "1.0.0",
                                    "published": "2020-01-01T00:00:00Z"
                                }
                            },
                            {
                                "catalogEntry": {
                                    "version": "1.1.0",
                                    "published": "2020-02-01T00:00:00Z"
                                }
                            }
                        ]
                    }
                ]
            })
        ]

        req = create_request("TestPackage", "1.0.0", ResolutionMode.EXACT)
        candidates = resolver.fetch_candidates(req)
        version, count, error = resolver.pick(req, candidates)

        assert version == "1.0.0"
        assert count == 2
        assert error is None

    @patch('src.versioning.resolvers.nuget.get_json')
    def test_v3_latest_version(self, mock_get_json, resolver):
        """Test latest version resolution via V3 API."""
        mock_get_json.side_effect = [
            (200, {}, {
                "version": "3.0.0",
                "resources": [
                    {
                        "@id": "https://api.nuget.org/v3/registration5-gz-semver2/",
                        "@type": "RegistrationsBaseUrl/3.6.0"
                    }
                ]
            }),
            (200, {}, {
                "items": [
                    {
                        "items": [
                            {
                                "catalogEntry": {
                                    "version": "1.0.0",
                                    "published": "2020-01-01T00:00:00Z"
                                }
                            },
                            {
                                "catalogEntry": {
                                    "version": "2.0.0",
                                    "published": "2020-02-01T00:00:00Z"
                                }
                            }
                        ]
                    }
                ]
            })
        ]

        req = create_request("TestPackage")
        candidates = resolver.fetch_candidates(req)
        version, count, error = resolver.pick(req, candidates)

        assert version == "2.0.0"
        assert count == 2
        assert error is None

    @patch('src.versioning.resolvers.nuget.get_json')
    def test_v2_fallback(self, mock_get_json, resolver):
        """Test V2 API fallback when V3 is unavailable."""
        # V3 fails, V2 succeeds
        mock_get_json.side_effect = [
            (404, {}, None),  # V3 service index fails
            (200, {}, {
                "d": {
                    "results": [
                        {"Version": "1.5.0"},
                        {"Version": "1.0.0"}
                    ]
                }
            })
        ]

        req = create_request("TestPackage")
        candidates = resolver.fetch_candidates(req)
        version, count, error = resolver.pick(req, candidates)

        assert version == "1.5.0"
        assert count == 2
        assert error is None

    def test_pick_latest_excludes_prerelease(self, resolver):
        """Test that latest mode excludes prerelease versions."""
        candidates = ["1.0.0", "1.1.0-beta", "2.0.0", "2.1.0-alpha"]
        version, count, error = resolver.pick(create_request("TestPackage"), candidates)

        assert version == "2.0.0"
        assert count == 4
        assert error is None

    def test_pick_exact_version_found(self, resolver):
        """Test exact version matching."""
        candidates = ["1.0.0", "1.1.0", "2.0.0"]
        req = create_request("TestPackage", "1.1.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, candidates)

        assert version == "1.1.0"
        assert count == 3
        assert error is None

    def test_pick_exact_version_not_found(self, resolver):
        """Test exact version matching when version doesn't exist."""
        candidates = ["1.0.0", "1.1.0", "2.0.0"]
        req = create_request("TestPackage", "1.5.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, candidates)

        assert version is None
        assert count == 3
        assert "not found" in error.lower()

    def test_pick_range_version(self, resolver):
        """Test range version matching."""
        candidates = ["1.0.0", "1.1.0", "1.2.0", "2.0.0"]
        req = create_request("TestPackage", "^1.0.0", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, candidates)

        assert version == "1.2.0"  # Highest matching version
        assert count == 4
        assert error is None

    def test_no_candidates(self, resolver):
        """Test handling when no candidates are available."""
        req = create_request("TestPackage")
        version, count, error = resolver.pick(req, [])

        assert version is None
        assert count == 0
        assert "no versions" in error.lower()
