"""Tests for provider validation service matching behaviors."""
import pytest
from unittest.mock import MagicMock

from metapackage import MetaPackage
from repository.provider_validation import ProviderValidationService
from repository.url_normalize import RepoRef


class MockProviderClient:
    """Mock provider client for testing."""

    _DEFAULT = object()

    def __init__(self, repo_info=_DEFAULT, releases=_DEFAULT, tags=_DEFAULT, contributors=None):
        # Differentiate between omitted args (use defaults) and explicit None (preserve None)
        if repo_info is self._DEFAULT:
            self.repo_info = {"stars": 100, "last_activity_at": "2023-01-01T00:00:00Z"}
        else:
            self.repo_info = repo_info

        if releases is self._DEFAULT:
            self.releases = []
        else:
            self.releases = releases

        if tags is self._DEFAULT:
            self.tags = []
        else:
            self.tags = tags

        self.contributors = contributors

    def get_repo_info(self, owner, repo):
        return self.repo_info

    def get_releases(self, owner, repo):
        return self.releases

    def get_tags(self, owner, repo):
        return self.tags

    def get_contributors_count(self, owner, repo):
        return self.contributors


class TestProviderValidationService:
    """Test ProviderValidationService matching behaviors."""

    def test_releases_to_tags_fallback_with_releases_no_match(self):
        """Test fallback to tags when releases exist but don't match version."""
        mp = MetaPackage("testpackage")
        ref = RepoRef("https://github.com/owner/repo", "github", "owner", "repo")

        # Releases don't match version, but tags do
        provider = MockProviderClient(
            releases=[{"name": "v2.0.0", "tag_name": "v2.0.0"}],
            tags=[{"name": "v1.2.3", "tag_name": "v1.2.3"}]
        )

        result = ProviderValidationService.validate_and_populate(mp, ref, "1.2.3", provider)

        assert result is True
        assert mp.repo_exists is True
        assert mp.repo_version_match["matched"] is True
        assert mp.repo_version_match["tag_or_release"] == "1.2.3"

    def test_releases_to_tags_fallback_with_releases_match(self):
        """Test that releases are preferred when they match."""
        mp = MetaPackage("testpackage")
        ref = RepoRef("https://github.com/owner/repo", "github", "owner", "repo")

        # Both releases and tags match, should prefer releases
        provider = MockProviderClient(
            releases=[{"name": "v1.2.3", "tag_name": "v1.2.3"}],
            tags=[{"name": "v1.2.3", "tag_name": "v1.2.3"}]
        )

        result = ProviderValidationService.validate_and_populate(mp, ref, "1.2.3", provider)

        assert result is True
        assert mp.repo_exists is True
        assert mp.repo_version_match["matched"] is True
        assert mp.repo_version_match["tag_or_release"] == "1.2.3"

    def test_empty_version_guard_no_matching(self):
        """Test that empty version disables matching but still populates repo data."""
        mp = MetaPackage("testpackage")
        ref = RepoRef("https://github.com/owner/repo", "github", "owner", "repo")

        # Tags that would match if version wasn't empty
        provider = MockProviderClient(
            releases=[{"name": "v1.2.3", "tag_name": "v1.2.3"}],
            tags=[{"name": "v1.2.3", "tag_name": "v1.2.3"}]
        )

        result = ProviderValidationService.validate_and_populate(mp, ref, "", provider)

        assert result is True
        assert mp.repo_exists is True
        assert mp.repo_stars == 100
        # Version match should indicate no match due to empty version
        assert mp.repo_version_match["matched"] is False

    def test_monorepo_tag_matching(self):
        """Test matching with monorepo-style tag names."""
        mp = MetaPackage("testpackage")
        ref = RepoRef("https://github.com/owner/repo", "github", "owner", "repo")

        provider = MockProviderClient(
            releases=[],  # No releases
            tags=[{"name": "react-router@7.8.2", "tag_name": "react-router@7.8.2"}]
        )

        result = ProviderValidationService.validate_and_populate(mp, ref, "7.8.2", provider)

        assert result is True
        assert mp.repo_exists is True
        assert mp.repo_version_match["matched"] is True
        assert mp.repo_version_match["tag_or_release"] == "7.8.2"

    def test_hyphen_underscore_tag_matching(self):
        """Test matching with hyphen/underscore suffixed tag names."""
        mp = MetaPackage("testpackage")
        ref = RepoRef("https://github.com/owner/repo", "github", "owner", "repo")

        provider = MockProviderClient(
            releases=[],  # No releases
            tags=[
                {"name": "react-router-7.8.2", "tag_name": "react-router-7.8.2"},
                {"name": "react_router_7.8.2", "tag_name": "react_router_7.8.2"}
            ]
        )

        result = ProviderValidationService.validate_and_populate(mp, ref, "7.8.2", provider)

        assert result is True
        assert mp.repo_exists is True
        assert mp.repo_version_match["matched"] is True
        assert mp.repo_version_match["tag_or_release"] == "7.8.2"

    def test_repo_not_found(self):
        """Test handling when repository doesn't exist."""
        mp = MetaPackage("testpackage")
        ref = RepoRef("https://github.com/owner/repo", "github", "owner", "repo")

        provider = MockProviderClient(repo_info=None)  # Repo not found

        result = ProviderValidationService.validate_and_populate(mp, ref, "1.2.3", provider)

        assert result is False
        assert mp.repo_exists is None

    def test_no_releases_no_tags(self):
        """Test behavior when neither releases nor tags are available."""
        mp = MetaPackage("testpackage")
        ref = RepoRef("https://github.com/owner/repo", "github", "owner", "repo")

        provider = MockProviderClient(releases=None, tags=None)

        result = ProviderValidationService.validate_and_populate(mp, ref, "1.2.3", provider)

        assert result is True
        assert mp.repo_exists is True
        assert mp.repo_version_match["matched"] is False
