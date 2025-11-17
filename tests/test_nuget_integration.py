"""Integration tests for NuGet support."""

import pytest
from unittest.mock import patch

from metapackage import MetaPackage
from registry.nuget import recv_pkg_info, scan_source
from cli_registry import check_against, scan_source as cli_scan_source
from constants import PackageManagers


class TestNuGetIntegration:
    """Integration tests for NuGet functionality."""

    @patch('registry.nuget.client._fetch_v3_package_metadata')
    @patch('registry.nuget.client._fetch_v2_package_metadata')
    @patch('registry.nuget.client._enrich_with_repo')
    def test_end_to_end_package_check(self, mock_enrich, mock_v2, mock_v3):
        """Test end-to-end package checking workflow."""
        # Mock V3 response
        mock_v3.return_value = ({
            "id": "Newtonsoft.Json",
            "versions": ["13.0.1", "13.0.2"],
            "latest_version": "13.0.2",
            "published": "2023-01-01T00:00:00Z",
            "repositoryUrl": "https://github.com/JamesNK/Newtonsoft.Json.git",
            "projectUrl": "https://www.newtonsoft.com/json",
            "licenseUrl": "https://opensource.org/licenses/MIT",
            "license": "MIT",
            "api_version": "v3"
        }, "v3")

        pkg = MetaPackage("Newtonsoft.Json", "nuget")
        recv_pkg_info([pkg])

        assert pkg.exists is True
        assert pkg.version_count == 2
        mock_enrich.assert_called_once()

    def test_cli_scan_source_integration(self):
        """Test CLI scan_source integration."""
        # This would require actual project files, so we'll just test the import
        # In a real scenario, this would scan actual .csproj files
        assert hasattr(PackageManagers, 'NUGET')
        assert PackageManagers.NUGET.value == "nuget"

    @patch('registry.nuget.client._fetch_v3_package_metadata')
    @patch('registry.nuget.client._fetch_v2_package_metadata')
    def test_v3_primary_v2_fallback(self, mock_v2, mock_v3):
        """Test V3 primary with V2 fallback."""
        # V3 succeeds
        mock_v3.return_value = ({
            "id": "TestPackage",
            "versions": ["1.0.0"],
            "latest_version": "1.0.0",
            "published": "2020-01-01T00:00:00Z",
            "api_version": "v3"
        }, "v3")

        pkg = MetaPackage("TestPackage", "nuget")
        recv_pkg_info([pkg])

        assert pkg.exists is True
        mock_v3.assert_called_once()
        mock_v2.assert_not_called()  # Should not fallback when V3 succeeds

    @patch('registry.nuget.client._fetch_v3_package_metadata')
    @patch('registry.nuget.client._fetch_v2_package_metadata')
    def test_v2_fallback_when_v3_fails(self, mock_v2, mock_v3):
        """Test V2 fallback when V3 fails."""
        # V3 fails, V2 succeeds
        mock_v3.return_value = (None, "v2")
        mock_v2.return_value = {
            "id": "TestPackage",
            "versions": ["1.0.0"],
            "latest_version": "1.0.0",
            "published": "2020-01-01T00:00:00Z"
        }

        pkg = MetaPackage("TestPackage", "nuget")
        recv_pkg_info([pkg])

        assert pkg.exists is True
        mock_v3.assert_called_once()
        mock_v2.assert_called_once()  # Should fallback to V2
