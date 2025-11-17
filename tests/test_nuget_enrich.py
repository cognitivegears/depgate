"""Tests for NuGet enrichment functionality."""

import pytest
from unittest.mock import patch, MagicMock

from metapackage import MetaPackage
from registry.nuget.enrich import _enrich_with_repo
from registry.nuget.discovery import _extract_repo_candidates


class TestEnrichWithRepo:
    """Test _enrich_with_repo function."""

    @patch('registry.nuget.enrich.nuget_pkg.normalize_repo_url')
    @patch('registry.nuget.enrich.map_host_to_type')
    @patch('registry.nuget.enrich.ProviderRegistry')
    @patch('registry.nuget.enrich.ProviderValidationService')
    def test_enriches_with_valid_repository(self, mock_validation, mock_registry, mock_map_host, mock_normalize):
        """Test enrichment with valid repository URL."""
        # Setup mocks
        normalized = MagicMock()
        normalized.normalized_url = "https://github.com/test/repo"
        normalized.host = "github.com"
        mock_normalize.return_value = normalized

        from repository.providers import ProviderType
        mock_map_host.return_value = ProviderType.GITHUB

        mock_provider = MagicMock()
        mock_registry.get.return_value = mock_provider

        # Create package and metadata
        pkg = MetaPackage("TestPackage", "nuget")
        metadata = {
            "id": "TestPackage",
            "latest_version": "1.0.0",
            "repositoryUrl": "https://github.com/test/repo.git",
            "projectUrl": "https://github.com/test/repo",
            "published": "2020-01-01T00:00:00Z"
        }

        _enrich_with_repo(pkg, metadata)

        assert pkg.repo_present_in_registry is True
        assert pkg.repo_url_normalized == "https://github.com/test/repo"
        mock_validation.validate_and_populate.assert_called_once()

    def test_handles_missing_latest_version(self):
        """Test handling when latest version is missing."""
        pkg = MetaPackage("TestPackage", "nuget")
        metadata = {
            "id": "TestPackage"
        }

        _enrich_with_repo(pkg, metadata)

        # Should not crash, but may not set repo fields
        assert not hasattr(pkg, 'repo_resolved') or not pkg.repo_resolved

    @patch('registry.nuget.enrich.nuget_pkg.normalize_repo_url')
    def test_handles_invalid_repository_url(self, mock_normalize):
        """Test handling of invalid repository URL."""
        mock_normalize.return_value = None

        pkg = MetaPackage("TestPackage", "nuget")
        metadata = {
            "id": "TestPackage",
            "latest_version": "1.0.0",
            "repositoryUrl": "invalid-url"
        }

        _enrich_with_repo(pkg, metadata)

        assert pkg.repo_present_in_registry is True
        assert hasattr(pkg, 'repo_errors')

    @patch('registry.nuget.enrich.depsdev_enrich')
    @patch('registry.nuget.enrich.osm_enrich')
    def test_integrates_with_depsdev_and_osm(self, mock_osm, mock_depsdev):
        """Test integration with deps.dev and OpenSourceMalware."""
        pkg = MetaPackage("TestPackage", "nuget")
        pkg.resolved_version = "1.0.0"
        metadata = {
            "id": "TestPackage",
            "latest_version": "1.0.0",
            "repositoryUrl": None,
            "projectUrl": None
        }

        _enrich_with_repo(pkg, metadata)

        # Verify OSM enrichment is called with correct parameters
        mock_osm.assert_called_once()
        call_args = mock_osm.call_args
        assert call_args[0][0] == pkg, "First argument should be the package"
        assert call_args[0][1] == "nuget", "Second argument should be 'nuget' ecosystem"
        assert call_args[0][2] == "TestPackage", "Third argument should be package name"
        assert call_args[0][3] == "1.0.0", "Fourth argument should be version (resolved_version)"

        # Verify deps.dev enrichment is also called
        mock_depsdev.assert_called_once()
        depsdev_call_args = mock_depsdev.call_args
        assert depsdev_call_args[0][0] == pkg, "First argument should be the package"
        assert depsdev_call_args[0][1] == "nuget", "Second argument should be 'nuget' ecosystem"

    def test_populates_license_information(self):
        """Test license information population."""
        pkg = MetaPackage("TestPackage", "nuget")
        metadata = {
            "id": "TestPackage",
            "latest_version": "1.0.0",
            "license": "MIT",
            "licenseUrl": "https://opensource.org/licenses/MIT",
            "repositoryUrl": None,
            "projectUrl": None
        }

        _enrich_with_repo(pkg, metadata)

        assert hasattr(pkg, 'license_id')
        assert pkg.license_id == "MIT"
        assert hasattr(pkg, 'license_available')
        assert pkg.license_available is True
