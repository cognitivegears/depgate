"""Tests for NuGet discovery functionality."""

import pytest

from registry.nuget.discovery import (
    _extract_repo_candidates,
    _extract_license_from_metadata,
)


class TestExtractRepoCandidates:
    """Test _extract_repo_candidates function."""

    def test_extracts_repository_url(self):
        """Test extraction of repositoryUrl."""
        metadata = {
            "repositoryUrl": "https://github.com/test/repo.git",
            "projectUrl": "https://github.com/test/repo"
        }

        candidates = _extract_repo_candidates(metadata)

        assert len(candidates) == 1
        assert "github.com/test/repo.git" in candidates[0]

    def test_falls_back_to_project_url(self):
        """Test fallback to projectUrl when repositoryUrl is missing."""
        metadata = {
            "projectUrl": "https://github.com/test/repo"
        }

        candidates = _extract_repo_candidates(metadata)

        assert len(candidates) == 1
        assert "github.com/test/repo" in candidates[0]

    def test_returns_empty_when_no_urls(self):
        """Test handling when no repository URLs are present."""
        metadata = {}

        candidates = _extract_repo_candidates(metadata)

        assert len(candidates) == 0

    def test_handles_string_repository_url(self):
        """Test handling of string repositoryUrl."""
        metadata = {
            "repositoryUrl": "https://github.com/test/repo.git"
        }

        candidates = _extract_repo_candidates(metadata)

        assert len(candidates) == 1
        assert candidates[0] == "https://github.com/test/repo.git"


class TestExtractLicenseFromMetadata:
    """Test _extract_license_from_metadata function."""

    def test_extracts_string_license(self):
        """Test extraction of string license."""
        metadata = {
            "license": "MIT",
            "licenseUrl": "https://opensource.org/licenses/MIT"
        }

        license_id, license_source, license_url = _extract_license_from_metadata(metadata)

        assert license_id == "MIT"
        assert license_source == "nuget_license"
        assert license_url == "https://opensource.org/licenses/MIT"

    def test_extracts_license_url_only(self):
        """Test extraction when only licenseUrl is present."""
        metadata = {
            "licenseUrl": "https://opensource.org/licenses/MIT"
        }

        license_id, license_source, license_url = _extract_license_from_metadata(metadata)

        assert license_id is None
        assert license_source == "nuget_licenseUrl"
        assert license_url == "https://opensource.org/licenses/MIT"

    def test_returns_none_when_no_license(self):
        """Test handling when no license information is present."""
        metadata = {}

        license_id, license_source, license_url = _extract_license_from_metadata(metadata)

        assert license_id is None
        assert license_source is None
        assert license_url is None

    def test_handles_dict_license(self):
        """Test handling of dictionary license field."""
        metadata = {
            "license": {
                "type": "MIT",
                "expression": "MIT"
            }
        }

        license_id, license_source, license_url = _extract_license_from_metadata(metadata)

        assert license_id == "MIT"
        assert license_source == "nuget_license"
