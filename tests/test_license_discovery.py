"""Tests for license discovery."""

import pytest
from unittest.mock import patch, MagicMock
from src.repository.license_discovery import LicenseDiscovery, license_discovery


class TestLicenseDiscovery:
    """Test LicenseDiscovery class."""

    def test_discover_license_github(self):
        """Test license discovery for GitHub URLs."""
        discovery = LicenseDiscovery()

        # Mock the cached function to return a result
        with patch.object(discovery, '_LicenseDiscovery__discover_license', return_value={
            "id": "MIT",
            "available": True,
            "source": "github_api"
        }):
            result = discovery.discover_license("https://github.com/user/repo", "default")
            assert result["id"] == "MIT"
            assert result["available"] is True
            assert result["source"] == "github_api"

    def test_discover_license_gitlab(self):
        """Test license discovery for GitLab URLs."""
        discovery = LicenseDiscovery()

        with patch.object(discovery, '_LicenseDiscovery__discover_license', return_value={
            "id": "Apache-2.0",
            "available": True,
            "source": "gitlab_api"
        }):
            result = discovery.discover_license("https://gitlab.com/user/repo", "default")
            assert result["id"] == "Apache-2.0"
            assert result["available"] is True

    def test_discover_license_unknown_provider(self):
        """Test license discovery for unknown providers."""
        discovery = LicenseDiscovery()

        with patch.object(discovery, '_LicenseDiscovery__discover_license', return_value={
            "id": None,
            "available": False,
            "source": "generic_fallback"
        }):
            result = discovery.discover_license("https://example.com/repo", "default")
            assert result["id"] is None
            assert result["available"] is False

    def test_caching(self):
        """Test that caching works correctly."""
        discovery = LicenseDiscovery()

        # Mock the implementation
        mock_impl = MagicMock(return_value={
            "id": "MIT",
            "available": True,
            "source": "test"
        })

        with patch.object(discovery, '_LicenseDiscovery__discover_license_impl', mock_impl):
            # First call
            result1 = discovery.discover_license("https://github.com/user/repo", "default")
            # Second call with same parameters
            result2 = discovery.discover_license("https://github.com/user/repo", "default")

            # Should only call implementation once due to caching
            assert mock_impl.call_count == 1
            assert result1 == result2

    def test_error_handling(self):
        """Test error handling in license discovery."""
        discovery = LicenseDiscovery()

        with patch.object(discovery, '_LicenseDiscovery__discover_license', side_effect=Exception("Network error")):
            result = discovery.discover_license("https://github.com/user/repo", "default")

            # Should return default values on error
            assert result["id"] is None
            assert result["available"] is False
            assert result["source"] is None

    def test_provider_identification(self):
        """Test provider identification from URLs."""
        discovery = LicenseDiscovery()

        assert discovery._identify_provider(type('MockURL', (), {'hostname': 'github.com'})()) == "github"
        assert discovery._identify_provider(type('MockURL', (), {'hostname': 'gitlab.com'})()) == "gitlab"
        assert discovery._identify_provider(type('MockURL', (), {'hostname': 'bitbucket.org'})()) == "other"


class TestGlobalLicenseDiscovery:
    """Test the global license_discovery instance."""

    def test_global_instance_exists(self):
        """Test that global instance exists."""
        assert license_discovery is not None
        assert isinstance(license_discovery, LicenseDiscovery)

    def test_global_instance_caching(self):
        """Test that global instance has caching."""
        # This is a basic smoke test
        result = license_discovery.discover_license("https://github.com/user/repo", "default")
        # Should not raise an exception
        assert isinstance(result, dict)
        assert "id" in result
        assert "available" in result
        assert "source" in result
