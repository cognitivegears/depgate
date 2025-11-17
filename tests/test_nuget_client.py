"""Tests for NuGet client functionality."""

import json
from unittest.mock import patch, MagicMock
import pytest

from metapackage import MetaPackage
from registry.nuget.client import (
    _fetch_v3_service_index,
    _get_v3_registration_url,
    _fetch_v3_package_metadata,
    _fetch_v2_package_metadata,
    _normalize_metadata,
    recv_pkg_info,
)
from registry.nuget.enrich import _enrich_with_repo


class TestFetchV3ServiceIndex:
    """Test V3 service index fetching."""

    @patch('registry.nuget.client.nuget_pkg.safe_get')
    def test_fetches_service_index_successfully(self, mock_safe_get):
        """Test successful service index fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "version": "3.0.0",
            "resources": []
        })
        mock_safe_get.return_value = mock_response

        result = _fetch_v3_service_index()

        assert result is not None
        assert result["version"] == "3.0.0"

    @patch('registry.nuget.client.nuget_pkg.safe_get')
    def test_handles_service_index_failure(self, mock_safe_get):
        """Test handling of service index fetch failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_safe_get.return_value = mock_response

        result = _fetch_v3_service_index()

        assert result is None


class TestGetV3RegistrationUrl:
    """Test V3 registration URL construction."""

    def test_constructs_registration_url(self):
        """Test registration URL construction from service index."""
        service_index = {
            "resources": [
                {
                    "@id": "https://api.nuget.org/v3/registration5-gz-semver2/",
                    "@type": "RegistrationsBaseUrl/3.6.0"
                }
            ]
        }

        url = _get_v3_registration_url("TestPackage", service_index)

        assert url is not None
        assert "testpackage" in url.lower()  # Package ID is lowercased in URL
        assert "index.json" in url

    def test_returns_none_when_no_registration_resource(self):
        """Test handling when registration resource is missing."""
        service_index = {
            "resources": [
                {
                    "@id": "https://api.nuget.org/v3/search/",
                    "@type": "SearchQueryService/3.0.0-beta"
                }
            ]
        }

        url = _get_v3_registration_url("TestPackage", service_index)

        assert url is None


class TestFetchV3PackageMetadata:
    """Test V3 package metadata fetching."""

    @patch('registry.nuget.client._fetch_v3_service_index')
    @patch('registry.nuget.client._get_v3_registration_url')
    @patch('registry.nuget.client.nuget_pkg.safe_get')
    def test_fetches_metadata_successfully(self, mock_safe_get, mock_get_url, mock_get_index):
        """Test successful metadata fetch via V3."""
        mock_get_index.return_value = {
            "resources": [
                {
                    "@id": "https://api.nuget.org/v3/registration5-gz-semver2/",
                    "@type": "RegistrationsBaseUrl/3.6.0"
                }
            ]
        }
        mock_get_url.return_value = "https://api.nuget.org/v3/registration5-gz-semver2/testpackage/index.json"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "items": [
                {
                    "items": [
                        {
                            "catalogEntry": {
                                "version": "1.0.0",
                                "published": "2020-01-01T00:00:00Z",
                                "projectUrl": "https://github.com/test/repo",
                                "repository": {
                                    "url": "https://github.com/test/repo.git"
                                }
                            }
                        }
                    ]
                }
            ]
        })
        mock_safe_get.return_value = mock_response

        metadata, api_version = _fetch_v3_package_metadata("TestPackage")

        assert metadata is not None
        assert api_version == "v3"
        assert metadata["latest_version"] == "1.0.0"
        assert metadata["repositoryUrl"] == "https://github.com/test/repo.git"

    @patch('registry.nuget.client._fetch_v3_service_index')
    def test_falls_back_to_v2_when_v3_unavailable(self, mock_get_index):
        """Test fallback to V2 when V3 is unavailable."""
        mock_get_index.return_value = None

        metadata, api_version = _fetch_v3_package_metadata("TestPackage")

        assert metadata is None
        assert api_version == "v2"


class TestFetchV2PackageMetadata:
    """Test V2 package metadata fetching."""

    @patch('registry.nuget.client.nuget_pkg.safe_get')
    def test_fetches_metadata_via_v2_json(self, mock_safe_get):
        """Test successful metadata fetch via V2 JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "d": {
                "results": [
                    {
                        "Id": "TestPackage",
                        "Version": "1.0.0",
                        "Published": "2020-01-01T00:00:00Z",
                        "ProjectUrl": "https://github.com/test/repo",
                        "LicenseUrl": "https://opensource.org/licenses/MIT"
                    }
                ]
            }
        })
        mock_safe_get.return_value = mock_response

        metadata = _fetch_v2_package_metadata("TestPackage")

        assert metadata is not None
        assert metadata["latest_version"] == "1.0.0"
        assert metadata["projectUrl"] == "https://github.com/test/repo"

    @patch('registry.nuget.client.nuget_pkg.safe_get')
    def test_handles_v2_failure(self, mock_safe_get):
        """Test handling of V2 fetch failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_safe_get.return_value = mock_response

        metadata = _fetch_v2_package_metadata("TestPackage")

        assert metadata is None


class TestNormalizeMetadata:
    """Test metadata normalization."""

    def test_normalizes_v3_metadata(self):
        """Test normalization of V3 metadata."""
        raw_metadata = {
            "id": "TestPackage",
            "versions": ["1.0.0", "1.1.0"],
            "latest_version": "1.1.0",
            "published": "2020-01-01T00:00:00Z",
            "projectUrl": "https://github.com/test/repo",
            "repositoryUrl": "https://github.com/test/repo.git",
            "licenseUrl": "https://opensource.org/licenses/MIT",
            "license": "MIT"
        }

        normalized = _normalize_metadata(raw_metadata, "v3")

        assert normalized["id"] == "TestPackage"
        assert normalized["api_version"] == "v3"
        assert normalized["latest_version"] == "1.1.0"

    def test_normalizes_v2_metadata(self):
        """Test normalization of V2 metadata."""
        raw_metadata = {
            "id": "TestPackage",
            "versions": ["1.0.0"],
            "latest_version": "1.0.0",
            "published": "2020-01-01T00:00:00Z",
            "projectUrl": "https://github.com/test/repo"
        }

        normalized = _normalize_metadata(raw_metadata, "v2")

        assert normalized["id"] == "TestPackage"
        assert normalized["api_version"] == "v2"


class TestRecvPkgInfo:
    """Test recv_pkg_info function."""

    @patch('registry.nuget.client._fetch_v3_package_metadata')
    @patch('registry.nuget.client._enrich_with_repo')
    def test_processes_packages_successfully(self, mock_enrich, mock_fetch):
        """Test successful package processing."""
        mock_fetch.return_value = ({
            "id": "TestPackage",
            "versions": ["1.0.0"],
            "latest_version": "1.0.0",
            "published": "2020-01-01T00:00:00Z",
            "projectUrl": "https://github.com/test/repo",
            "repositoryUrl": None,
            "licenseUrl": None,
            "license": None,
            "api_version": "v3"
        }, "v3")

        pkg = MetaPackage("TestPackage", "nuget")
        recv_pkg_info([pkg])

        assert pkg.exists is True
        assert pkg.version_count == 1
        mock_enrich.assert_called_once()

    @patch('registry.nuget.client._fetch_v3_package_metadata')
    @patch('registry.nuget.client._fetch_v2_package_metadata')
    def test_falls_back_to_v2(self, mock_fetch_v2, mock_fetch_v3):
        """Test fallback to V2 when V3 fails."""
        mock_fetch_v3.return_value = (None, "v2")
        mock_fetch_v2.return_value = {
            "id": "TestPackage",
            "versions": ["1.0.0"],
            "latest_version": "1.0.0",
            "published": "2020-01-01T00:00:00Z",
            "projectUrl": None,
            "repositoryUrl": None,
            "licenseUrl": None,
            "license": None
        }

        pkg = MetaPackage("TestPackage", "nuget")
        recv_pkg_info([pkg])

        assert pkg.exists is True
        mock_fetch_v2.assert_called_once()

    @patch('registry.nuget.client._fetch_v3_package_metadata')
    @patch('registry.nuget.client._fetch_v2_package_metadata')
    def test_handles_package_not_found(self, mock_fetch_v2, mock_fetch_v3):
        """Test handling when package is not found."""
        mock_fetch_v3.return_value = (None, "v2")
        mock_fetch_v2.return_value = None

        pkg = MetaPackage("NonExistentPackage", "nuget")
        recv_pkg_info([pkg])

        assert pkg.exists is False
